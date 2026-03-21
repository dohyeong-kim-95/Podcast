import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.reauth_host import HostedReauthSession


MOCK_USER = {
    "uid": "test-uid",
    "email": "test@example.com",
    "name": "Test User",
}


def _auth_patch():
    return patch("app.middleware.auth.verify_access_token", return_value=MOCK_USER)


async def _request(method: str, path: str, *, headers: dict[str, str] | None = None, json: dict | None = None):
    request_headers = {"Authorization": "Bearer valid-token"}
    if headers:
        request_headers.update(headers)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as api:
        return await api.request(method, path, headers=request_headers, json=json)


def _empty_db_context(*, row):
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = None
    cursor.fetchone.return_value = row
    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.__exit__.return_value = None
    conn.cursor.return_value = cursor
    return conn


def test_start_auth_reuses_running_session():
    current = {
        "sessionId": "s1",
        "status": "running",
        "viewerUrl": "https://viewer.example",
        "authFlow": "remote_vnc",
    }
    with _auth_patch(), patch("app.routers.nb_session._read_current_auth_session", return_value=current):
        response = asyncio.run(_request("POST", "/api/nb-session/start-auth"))

    assert response.status_code == 200
    body = response.json()
    assert body["sessionId"] == "s1"
    assert body["status"] == "pending"
    assert body["authFlow"] == "remote_vnc"


def test_start_auth_starts_new_session():
    session = HostedReauthSession(
        session_id="new-session",
        viewer_url="https://reauth.example/session/new-session",
        status="pending",
        auth_flow="remote_vnc",
    )
    with _auth_patch(), \
         patch("app.routers.nb_session._read_current_auth_session", return_value=None), \
         patch("app.routers.nb_session.create_reauth_session", new=AsyncMock(return_value=session)), \
         patch("app.routers.nb_session._callback_url", return_value="https://api.example/api/nb-session/internal/update"), \
         patch("app.routers.nb_session._callback_token", return_value="callback-secret"), \
         patch("app.routers.nb_session._write_auth_session") as mock_write:
        response = asyncio.run(_request("POST", "/api/nb-session/start-auth"))

    assert response.status_code == 200
    body = response.json()
    assert body["sessionId"] == "new-session"
    assert body["viewerUrl"] == "https://reauth.example/session/new-session"
    assert body["status"] == "pending"
    assert body["authFlow"] == "remote_vnc"
    assert mock_write.call_count == 1


def test_poll_not_found():
    with _auth_patch(), patch("app.routers.nb_session._read_auth_session", return_value=None):
        response = asyncio.run(_request("GET", "/api/nb-session/poll/missing"))

    assert response.status_code == 404
    assert response.json()["detail"] == "Auth session not found"


def test_poll_running_normalizes_to_pending():
    with _auth_patch(), patch("app.routers.nb_session._read_auth_session", return_value={
        "sessionId": "s1",
        "status": "running",
        "viewerUrl": "https://viewer",
        "authFlow": "remote_vnc",
        "error": None,
        "completedAt": None,
    }):
        response = asyncio.run(_request("GET", "/api/nb-session/poll/s1"))

    assert response.status_code == 200
    assert response.json()["status"] == "pending"


def test_status_without_auth_session():
    row = {"auth_flow": "remote_vnc", "expires_at": None, "last_updated": None, "status": "missing"}
    with _auth_patch(), \
         patch("app.routers.nb_session.get_db", return_value=_empty_db_context(row=row)), \
         patch("app.routers.nb_session._read_current_auth_session", return_value=None):
        response = asyncio.run(_request("GET", "/api/nb-session/status"))

    assert response.status_code == 200
    assert response.json()["status"] in {"missing", "expired"}
    assert response.json()["authSession"] is None


def test_provider_update_marks_completed():
    with patch("app.routers.nb_session._callback_token", return_value="callback-secret"), \
         patch("app.routers.nb_session._read_auth_session_owner", return_value={
             "uid": "test-uid",
             "viewerUrl": "https://viewer",
             "authFlow": "remote_vnc",
         }), \
         patch("app.routers.nb_session.save_nb_session", new=AsyncMock(return_value={
             "status": "valid",
             "expiresAt": datetime.now(timezone.utc),
             "authFlow": "remote_vnc",
         })), \
         patch("app.routers.nb_session._write_auth_session") as mock_write:
        response = asyncio.run(
            _request(
                "POST",
                "/api/nb-session/internal/update",
                headers={"Authorization": "Bearer callback-secret"},
                json={
                    "sessionId": "s1",
                    "status": "completed",
                    "storageState": {"cookies": []},
                },
            )
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert mock_write.call_count == 1
    payload = mock_write.call_args.args[2]
    assert payload["status"] == "completed"


def test_provider_update_rejects_invalid_storage_state():
    with patch("app.routers.nb_session._callback_token", return_value="callback-secret"), \
         patch("app.routers.nb_session._read_auth_session_owner", return_value={
             "uid": "test-uid",
             "viewerUrl": "https://viewer",
             "authFlow": "remote_vnc",
         }), \
         patch("app.routers.nb_session.save_nb_session", new=AsyncMock(side_effect=ValueError("NB session storage state missing required cookies: SID"))), \
         patch("app.routers.nb_session._write_auth_session") as mock_write:
        response = asyncio.run(
            _request(
                "POST",
                "/api/nb-session/internal/update",
                headers={"Authorization": "Bearer callback-secret"},
                json={
                    "sessionId": "s1",
                    "status": "completed",
                    "storageState": {"cookies": []},
                },
            )
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    payload = mock_write.call_args.args[2]
    assert payload["status"] == "failed"
    assert "required cookies: SID" in payload["error"]


def test_provider_update_marks_timeout():
    with patch("app.routers.nb_session._callback_token", return_value="callback-secret"), \
         patch("app.routers.nb_session._read_auth_session_owner", return_value={
             "uid": "test-uid",
             "viewerUrl": "https://viewer",
             "authFlow": "remote_vnc",
         }), \
         patch("app.routers.nb_session._write_auth_session") as mock_write:
        response = asyncio.run(
            _request(
                "POST",
                "/api/nb-session/internal/update",
                headers={"Authorization": "Bearer callback-secret"},
                json={
                    "sessionId": "s1",
                    "status": "timed_out",
                    "error": "login timed out",
                },
            )
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert mock_write.call_count == 1
    payload = mock_write.call_args.args[2]
    assert payload["status"] == "timed_out"
    assert payload["error"] == "login timed out"
