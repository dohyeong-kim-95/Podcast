"""Phase 6: NB session re-authentication API tests."""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient

_FIREBASE_INIT_PATCHER = patch("app.main.init_firebase", return_value=None)
_FIREBASE_INIT_PATCHER.start()

from app.main import app
from app.services.browserless import BrowserlessSession


@asynccontextmanager
async def _test_lifespan(_app):
    yield


app.router.lifespan_context = _test_lifespan

MOCK_USER = {
    "uid": "test-uid",
    "email": "test@gmail.com",
    "name": "Test User",
}
AUTH_HEADERS = {"Authorization": "Bearer valid-token"}


def _auth_patch():
    return patch("app.middleware.auth.verify_id_token", return_value=MOCK_USER)


def _db_with_nb_session_doc(*, exists: bool, data: dict | None = None):
    doc = MagicMock()
    doc.exists = exists
    doc.to_dict.return_value = data or {}

    nb_session_doc_ref = MagicMock()
    nb_session_doc_ref.get.return_value = doc

    nb_session_collection = MagicMock()
    nb_session_collection.document.return_value = nb_session_doc_ref

    user_doc_ref = MagicMock()
    user_doc_ref.collection.return_value = nb_session_collection

    users_collection = MagicMock()
    users_collection.document.return_value = user_doc_ref

    db = MagicMock()
    db.collection.return_value = users_collection
    return db


async def _request(method: str, path: str, *, headers: dict | None = None):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.request(method, path, headers=headers)


class TestStartAuth:
    def test_no_auth(self):
        response = asyncio.run(_request("POST", "/api/nb-session/start-auth"))
        assert response.status_code == 401

    def test_reuses_active_auth_session(self):
        active = {
            "sessionId": "existing-session",
            "status": "running",
            "viewerUrl": "https://viewer.example.com",
        }
        with _auth_patch(), \
             patch("app.routers.nb_session._read_current_auth_session", return_value=active), \
             patch("app.routers.nb_session.create_browserless_session") as mock_create:
            response = asyncio.run(_request("POST", "/api/nb-session/start-auth", headers=AUTH_HEADERS))

        assert response.status_code == 200
        assert response.json()["sessionId"] == "existing-session"
        assert response.json()["status"] == "pending"
        mock_create.assert_not_called()

    def test_starts_new_auth_session(self):
        session = BrowserlessSession(
            session_id="session-123",
            connect_url="wss://browserless.example.com",
            viewer_url="https://viewer.example.com",
            target_url="https://notebooklm.google.com",
            timeout_seconds=300,
        )

        with _auth_patch(), \
             patch("app.routers.nb_session._read_current_auth_session", return_value=None), \
             patch("app.routers.nb_session.create_browserless_session", return_value=session), \
             patch("app.routers.nb_session._write_auth_session") as mock_write, \
             patch("app.routers.nb_session._run_auth_flow", new=AsyncMock()) as mock_flow:
            response = asyncio.run(_request("POST", "/api/nb-session/start-auth", headers=AUTH_HEADERS))

        assert response.status_code == 200
        body = response.json()
        assert body["sessionId"] == "session-123"
        assert body["viewerUrl"] == "https://viewer.example.com"
        assert body["status"] == "pending"
        mock_write.assert_called_once()
        mock_flow.assert_awaited_once()


class TestPollAuthSession:
    def test_not_found(self):
        with _auth_patch(), \
             patch("app.routers.nb_session._read_auth_session", return_value=None):
            response = asyncio.run(_request("GET", "/api/nb-session/poll/missing", headers=AUTH_HEADERS))

        assert response.status_code == 404

    def test_running_session_normalizes_to_pending(self):
        session = {
            "sessionId": "session-123",
            "status": "running",
            "viewerUrl": "https://viewer.example.com",
            "authFlow": "new_tab",
        }
        with _auth_patch(), \
             patch("app.routers.nb_session._read_auth_session", return_value=session):
            response = asyncio.run(_request("GET", "/api/nb-session/poll/session-123", headers=AUTH_HEADERS))

        assert response.status_code == 200
        assert response.json()["status"] == "pending"


class TestGetNbSessionStatus:
    def test_missing_session(self):
        db = _db_with_nb_session_doc(exists=False)
        with _auth_patch(), \
             patch("app.routers.nb_session.get_firestore_client", return_value=db), \
             patch("app.routers.nb_session._read_current_auth_session", return_value=None):
            response = asyncio.run(_request("GET", "/api/nb-session/status", headers=AUTH_HEADERS))

        assert response.status_code == 200
        assert response.json() == {
            "status": "missing",
            "authFlow": None,
            "expiresAt": None,
            "lastUpdated": None,
            "authSession": None,
        }

    def test_includes_current_auth_session(self):
        expires_at = datetime.now(timezone.utc) + timedelta(days=10)
        last_updated = datetime.now(timezone.utc)
        db = _db_with_nb_session_doc(
            exists=True,
            data={
                "status": "valid",
                "authFlow": "new_tab",
                "expiresAt": expires_at,
                "lastUpdated": last_updated,
            },
        )
        current_auth = {
            "sessionId": "session-123",
            "status": "running",
            "viewerUrl": "https://viewer.example.com",
            "authFlow": "new_tab",
        }

        with _auth_patch(), \
             patch("app.routers.nb_session.get_firestore_client", return_value=db), \
             patch("app.routers.nb_session._read_current_auth_session", return_value=current_auth):
            response = asyncio.run(_request("GET", "/api/nb-session/status", headers=AUTH_HEADERS))

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "valid"
        assert body["authFlow"] == "new_tab"
        assert body["authSession"]["sessionId"] == "session-123"
        assert body["authSession"]["status"] == "pending"


class TestRunAuthFlow:
    def test_completed_marks_auth_session(self):
        session = BrowserlessSession(
            session_id="session-123",
            connect_url="wss://browserless.example.com",
            viewer_url="https://viewer.example.com",
            target_url="https://notebooklm.google.com",
            timeout_seconds=300,
        )
        expires_at = datetime.now(timezone.utc) + timedelta(days=30)
        session_meta = {
            "status": "valid",
            "expiresAt": expires_at,
            "authFlow": "new_tab",
        }

        with patch("app.routers.nb_session.wait_for_notebook_login", new=AsyncMock(return_value={"cookies": []})), \
             patch("app.routers.nb_session.save_nb_session", new=AsyncMock(return_value=session_meta)) as mock_save, \
             patch("app.routers.nb_session._write_auth_session") as mock_write:
            from app.routers.nb_session import _run_auth_flow

            asyncio.run(_run_auth_flow("test-uid", session))

        assert mock_save.await_count == 1
        mock_save.assert_awaited_once_with("test-uid", {"cookies": []}, auth_flow="new_tab")
        assert mock_write.call_count == 2
        assert mock_write.call_args_list[-1].args[2]["status"] == "completed"
        assert mock_write.call_args_list[-1].args[2]["nbSessionStatus"] == "valid"

    def test_generic_exception_marks_auth_session(self):
        session = BrowserlessSession(
            session_id="session-123",
            connect_url="wss://browserless.example.com",
            viewer_url="https://viewer.example.com",
            target_url="https://notebooklm.google.com",
            timeout_seconds=300,
        )

        with patch("app.routers.nb_session.wait_for_notebook_login", new=AsyncMock(side_effect=RuntimeError("boom"))), \
             patch("app.routers.nb_session._write_auth_session") as mock_write:
            from app.routers.nb_session import _run_auth_flow

            asyncio.run(_run_auth_flow("test-uid", session))

        assert mock_write.call_count == 2
        assert mock_write.call_args_list[-1].args[2]["status"] == "failed"

    def test_timeout_marks_auth_session(self):
        session = BrowserlessSession(
            session_id="session-123",
            connect_url="wss://browserless.example.com",
            viewer_url="https://viewer.example.com",
            target_url="https://notebooklm.google.com",
            timeout_seconds=300,
        )

        with patch("app.routers.nb_session.wait_for_notebook_login", new=AsyncMock(side_effect=TimeoutError("timed out"))), \
             patch("app.routers.nb_session._write_auth_session") as mock_write:
            from app.routers.nb_session import _run_auth_flow

            asyncio.run(_run_auth_flow("test-uid", session))

        assert mock_write.call_count == 2
        assert mock_write.call_args_list[-1].args[2]["status"] == "timed_out"
