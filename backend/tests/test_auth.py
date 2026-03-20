from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


MOCK_USER = {
    "uid": "test-uid",
    "email": "test@example.com",
    "name": "Test User",
}


def _auth_patch():
    return patch("app.middleware.auth.verify_access_token", return_value=MOCK_USER)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_verify_requires_bearer_token():
    response = client.post("/api/auth/verify")
    assert response.status_code == 401


def test_verify_rejects_invalid_access_token():
    with patch("app.middleware.auth.verify_access_token", side_effect=RuntimeError("invalid")):
        response = client.post(
            "/api/auth/verify",
            headers={"Authorization": "Bearer bad-token"},
        )
        assert response.status_code == 401


def test_verify_returns_user_profile():
    with _auth_patch(), patch(
        "app.routers.auth.upsert_user_profile"
    ) as mock_upsert:
        response = client.post(
            "/api/auth/verify",
            headers={"Authorization": "Bearer valid-token"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "uid": "test-uid",
        "email": "test@example.com",
        "name": "Test User",
    }
    mock_upsert.assert_called_once_with("test-uid", "test@example.com", "Test User")


def test_verify_rejects_not_allowed_email():
    with _auth_patch(), patch.dict("os.environ", {"ALLOWED_EMAILS": "allowed@example.com"}):
        response = client.post(
            "/api/auth/verify",
            headers={"Authorization": "Bearer valid-token"},
        )
    assert response.status_code == 403
    assert response.json()["detail"] == "Access denied: email not in whitelist"


def test_verify_allows_whitelisted_email_case_insensitive():
    allowed_user = {
        "uid": "test-uid",
        "email": "test@example.com",
        "name": "Test User",
    }
    with patch("app.middleware.auth.verify_access_token", return_value=allowed_user), \
         patch("app.routers.auth.upsert_user_profile"), \
         patch.dict("os.environ", {"ALLOWED_EMAILS": "TEST@EXAMPLE.COM,OTHER@example.com"}):
        response = client.post(
            "/api/auth/verify",
            headers={"Authorization": "Bearer valid-token"},
        )
    assert response.status_code == 200
