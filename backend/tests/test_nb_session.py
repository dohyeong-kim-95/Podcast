import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.main import app
from app.services.browserless import BrowserlessSession

from app.routers import nb_session as nb_session_router
from httpx import ASGITransport, AsyncClient


MOCK_USER = {
    "uid": "test-uid",
    "email": "test@example.com",
    "name": "Test User",
}


def _auth_patch():
    return patch("app.middleware.auth.verify_access_token", return_value=MOCK_USER)


async def _request(method: str, path: str):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as api:
        return await api.request(method, path, headers={"Authorization": "Bearer valid-token"})


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
    }
    with _auth_patch(), patch("app.routers.nb_session._read_current_auth_session", return_value=current):
        response = asyncio.run(_request("POST", "/api/nb-session/start-auth"))

    assert response.status_code == 200
    body = response.json()
    assert body["sessionId"] == "s1"
    assert body["status"] == "pending"


def test_start_auth_starts_new_session():
    session = BrowserlessSession(
        session_id="new-session",
        connect_url="wss://connect",
        viewer_url="https://viewer",
        target_url="https://notebooklm.google.com",
        timeout_seconds=300,
    )
    with _auth_patch(), \
         patch("app.routers.nb_session._read_current_auth_session", return_value=None), \
         patch("app.routers.nb_session.create_browserless_session", return_value=session), \
         patch("app.routers.nb_session._write_auth_session"), \
         patch("app.routers.nb_session._run_auth_flow", new=AsyncMock()):
        response = asyncio.run(_request("POST", "/api/nb-session/start-auth"))

    assert response.status_code == 200
    body = response.json()
    assert body["sessionId"] == "new-session"
    assert body["viewerUrl"] == "https://viewer"
    assert body["status"] == "pending"


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
        "authFlow": "new_tab",
        "error": None,
        "completedAt": None,
    }):
        response = asyncio.run(_request("GET", "/api/nb-session/poll/s1"))

    assert response.status_code == 200
    assert response.json()["status"] == "pending"


def test_status_without_auth_session():
    row = {"auth_flow": "new_tab", "expires_at": None, "last_updated": None, "status": "missing"}
    with _auth_patch(), \
         patch("app.routers.nb_session.get_db", return_value=_empty_db_context(row=row)), \
         patch("app.routers.nb_session._read_current_auth_session", return_value=None):
        response = asyncio.run(_request("GET", "/api/nb-session/status"))

    assert response.status_code == 200
    assert response.json()["status"] in {"missing", "expired"}
    assert response.json()["authSession"] is None


def test_run_auth_flow_marks_completed():
    session = BrowserlessSession(
        session_id="s1",
        connect_url="wss://connect",
        viewer_url="https://viewer",
        target_url="https://notebooklm.google.com",
        timeout_seconds=30,
    )

    with patch("app.routers.nb_session.wait_for_notebook_login", new=AsyncMock(return_value={"cookies": []})), \
         patch("app.routers.nb_session.save_nb_session", new=AsyncMock(return_value={
             "status": "valid",
             "expiresAt": datetime.now(timezone.utc),
             "authFlow": "new_tab",
         })), \
         patch("app.routers.nb_session._write_auth_session") as mock_write:
        asyncio.run(nb_session_router._run_auth_flow("test-uid", session))

    assert mock_write.call_count == 2


def test_run_auth_flow_marks_failed_on_timeout():
    session = BrowserlessSession(
        session_id="s1",
        connect_url="wss://connect",
        viewer_url="https://viewer",
        target_url="https://notebooklm.google.com",
        timeout_seconds=1,
    )

    with patch("app.routers.nb_session.wait_for_notebook_login", new=AsyncMock(side_effect=TimeoutError("timed out"))), \
         patch("app.routers.nb_session._write_auth_session") as mock_write:
        asyncio.run(nb_session_router._run_auth_flow("test-uid", session))

    assert mock_write.call_count == 2
    last_call = mock_write.call_args_list[-1]
    assert last_call.args[2]["status"] == "timed_out"
