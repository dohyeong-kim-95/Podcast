"""Phase 7: push token and reminder API tests."""

from datetime import datetime, timedelta, timezone
import asyncio
from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch

from httpx import ASGITransport, AsyncClient

_FIREBASE_INIT_PATCHER = patch("app.main.init_firebase", return_value=None)
_FIREBASE_INIT_PATCHER.start()

from app.main import app


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


def _scheduler_patch():
    return patch(
        "app.middleware.auth.google_id_token.verify_oauth2_token",
        return_value={
            "email": "scheduler@project.iam.gserviceaccount.com",
            "aud": "https://podcast-test.run.app",
        },
    )


def _scheduler_env():
    return patch.dict(
        "os.environ",
        {
            "CLOUD_RUN_URL": "https://podcast-test.run.app",
            "SCHEDULER_SERVICE_ACCOUNT": "scheduler@project.iam.gserviceaccount.com",
        },
    )


async def _request(method: str, path: str, *, headers: dict | None = None, json: dict | None = None):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.request(method, path, headers=headers, json=json)


class TestAuthVerify:
    def test_verify_upserts_user_profile(self):
        with _auth_patch(), \
             patch("app.routers.auth.upsert_user_profile") as mock_upsert:
            response = asyncio.run(_request("POST", "/api/auth/verify", headers=AUTH_HEADERS))

        assert response.status_code == 200
        mock_upsert.assert_called_once_with("test-uid", "test@gmail.com", "Test User")


class TestPushToken:
    def test_push_token_no_auth(self):
        response = asyncio.run(_request("POST", "/api/push-token", json={"token": "abc"}))
        assert response.status_code == 401

    def test_push_token_success(self):
        with _auth_patch(), \
             patch("app.routers.push.save_push_token") as mock_save:
            response = asyncio.run(
                _request("POST", "/api/push-token", headers=AUTH_HEADERS, json={"token": "abc-token"})
            )

        assert response.status_code == 200
        assert response.json() == {"registered": True}
        mock_save.assert_called_once_with(
            "test-uid",
            "abc-token",
            email="test@gmail.com",
            display_name="Test User",
        )


class TestRemindDownload:
    def test_remind_download_rejects_invalid_token(self):
        response = asyncio.run(_request("POST", "/api/remind-download"))
        assert response.status_code == 401

    def test_remind_download_sends_only_eligible_users(self):
        completed = MagicMock()
        completed.to_dict.return_value = {
            "uid": "user-a",
            "date": "2026-03-19",
            "status": "completed",
            "downloaded": False,
        }
        skipped = MagicMock()
        skipped.to_dict.return_value = {
            "uid": "user-b",
            "date": "2026-03-19",
            "status": "completed",
            "downloaded": True,
        }

        query = MagicMock()
        query.stream.return_value = [completed, skipped]
        collection = MagicMock()
        collection.where.return_value = query
        db = MagicMock()
        db.collection.return_value = collection

        with _scheduler_env(), _scheduler_patch(), \
             patch("app.routers.push.get_firestore_client", return_value=db), \
             patch("app.routers.push.send_push_to_user", return_value=True) as mock_send:
            response = asyncio.run(_request("POST", "/api/remind-download", headers=AUTH_HEADERS))

        assert response.status_code == 200
        body = response.json()
        assert body["sentCount"] == 1
        assert body["reminded"] == ["user-a"]
        assert db.collection.call_args_list[0][0][0] == "podcasts"
        now = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d")
        db.collection.return_value.where.assert_called_once_with("date", "==", now)
        mock_send.assert_called_once()

    def test_remind_download_skips_invalid_payload_users(self):
        missing_uid = MagicMock()
        missing_uid.to_dict.return_value = {
            "uid": None,
            "date": "2026-03-19",
            "status": "completed",
            "downloaded": False,
        }

        query = MagicMock()
        query.stream.return_value = [missing_uid]
        collection = MagicMock()
        collection.where.return_value = query
        db = MagicMock()
        db.collection.return_value = collection

        with _scheduler_env(), _scheduler_patch(), \
             patch("app.routers.push.get_firestore_client", return_value=db), \
             patch("app.routers.push.send_push_to_user", return_value=True) as mock_send:
            response = asyncio.run(_request("POST", "/api/remind-download", headers=AUTH_HEADERS))

        assert response.status_code == 200
        body = response.json()
        assert body["sentCount"] == 0
        assert body["reminded"] == []
        assert body["skippedCount"] == 1
        mock_send.assert_not_called()


class TestNotificationsService:
    def test_send_push_includes_link_payload(self):
        with patch("app.services.notifications.get_push_token", return_value="good-token"), \
             patch("app.services.notifications.messaging.send", return_value="message-id") as mock_send:
            from app.services.notifications import send_push_to_user

            result = send_push_to_user(
                "test-uid",
                title="title",
                body="body",
                link="/settings",
            )

        assert result is True
        message = mock_send.call_args.args[0]
        assert message.data == {"url": "/settings"}
        assert message.webpush.data == {"url": "/settings"}
        assert message.webpush.notification.data == {"url": "/settings"}
        assert message.webpush.fcm_options.link == "/settings"

    def test_invalid_token_clears_saved_token(self):
        with patch("app.services.notifications.get_push_token", return_value="bad-token"), \
             patch("app.services.notifications.messaging.send", side_effect=Exception("UNREGISTERED")), \
             patch("app.services.notifications.clear_push_token") as mock_clear:
            from app.services.notifications import send_push_to_user

            result = send_push_to_user(
                "test-uid",
                title="title",
                body="body",
                link="/",
            )

        assert result is False
        mock_clear.assert_called_once_with("test-uid")
