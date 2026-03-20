from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


MOCK_USER = {
    "uid": "test-uid",
    "email": "test@example.com",
    "name": "Test User",
}


SUBSCRIPTION_PAYLOAD = {
    "subscription": {
        "endpoint": "https://example.com/push",
        "expirationTime": None,
        "keys": {
            "p256dh": "p256",
            "auth": "auth",
        },
    }
}


def _auth_patch():
    return patch("app.middleware.auth.verify_access_token", return_value=MOCK_USER)


def test_push_token_no_auth():
    response = client.post("/api/push-token", json=SUBSCRIPTION_PAYLOAD)
    assert response.status_code == 401


def test_push_token_stores_subscription():
    with _auth_patch(), patch(
        "app.routers.push.save_push_subscription",
    ) as mock_save:
        response = client.post(
            "/api/push-token",
            headers={"Authorization": "Bearer valid-token"},
            json=SUBSCRIPTION_PAYLOAD,
        )

    assert response.status_code == 200
    assert response.json() == {"registered": True}
    mock_save.assert_called_once_with(
        "test-uid",
        SUBSCRIPTION_PAYLOAD["subscription"],
        email="test@example.com",
        display_name="Test User",
    )


def test_remind_download_sends_only_completed_not_downloaded():
    rows = [
        {"user_id": "user-a"},
        {"user_id": None},
    ]
    cursor = MagicMock()
    cursor.fetchone.side_effect = [None, None]
    cursor.fetchall.return_value = rows
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = None
    conn = MagicMock()
    conn.cursor.return_value = cursor
    conn.__enter__.return_value = conn
    conn.__exit__.return_value = None

    with patch.dict("os.environ", {"CLOUD_RUN_URL": "https://podcast.test"}), \
         patch("app.middleware.auth.google_id_token.verify_oauth2_token", return_value={"email": "scheduler@project.iam.gserviceaccount.com"}), \
         patch("app.routers.push.get_db", return_value=conn), \
         patch("app.routers.push.send_push_to_user", side_effect=[True, False]):
        response = client.post("/api/remind-download", headers={"Authorization": "Bearer scheduler-token"})

    assert response.status_code == 200
    assert response.json()["status"] == "done"
    assert response.json()["sentCount"] == 1
    assert response.json()["skippedCount"] == 1
    assert response.json()["reminded"] == ["user-a"]


def test_send_push_to_user_skips_when_no_subscription():
    with patch("app.services.notifications.get_push_subscription", return_value=None):
        from app.services.notifications import send_push_to_user

        result = send_push_to_user("test-uid", title="t", body="b", link="/")
        assert result is False


def test_send_push_to_user_clears_invalid_subscription():
    with patch("app.services.notifications.get_push_subscription", return_value={"endpoint": "e"}), \
         patch("app.services.notifications.webpush", side_effect=Exception("410")) as mock_webpush, \
         patch("app.services.notifications._is_invalid_subscription_error", return_value=True), \
         patch("app.services.notifications._vapid_private_key", return_value="private"), \
         patch("app.services.notifications._vapid_subject", return_value="mailto:test@example.com"), \
         patch("app.services.notifications.clear_push_subscription") as mock_clear:
        from app.services.notifications import send_push_to_user

        result = send_push_to_user("test-uid", title="t", body="b")
        assert result is False
        mock_webpush.assert_called_once()
        mock_clear.assert_called_once_with("test-uid")
