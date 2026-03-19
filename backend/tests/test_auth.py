from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_verify_no_token():
    response = client.post("/api/auth/verify")
    assert response.status_code == 401


def test_verify_invalid_token():
    with patch("app.middleware.auth.verify_id_token", side_effect=Exception("Invalid")):
        response = client.post(
            "/api/auth/verify",
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert response.status_code == 401


def test_verify_valid_token():
    mock_decoded = {
        "uid": "test-uid",
        "email": "test@gmail.com",
        "name": "Test User",
    }
    with patch("app.middleware.auth.verify_id_token", return_value=mock_decoded), \
         patch("app.routers.auth.upsert_user_profile"), \
         patch.dict("os.environ", {"ALLOWED_EMAILS": ""}):
            response = client.post(
                "/api/auth/verify",
                headers={"Authorization": "Bearer valid-token"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["uid"] == "test-uid"
            assert data["email"] == "test@gmail.com"


def test_verify_whitelist_denied():
    mock_decoded = {
        "uid": "test-uid",
        "email": "notallowed@gmail.com",
        "name": "Test User",
    }
    with patch("app.middleware.auth.verify_id_token", return_value=mock_decoded):
        with patch.dict("os.environ", {"ALLOWED_EMAILS": "allowed@gmail.com"}):
            response = client.post(
                "/api/auth/verify",
                headers={"Authorization": "Bearer valid-token"},
            )
            assert response.status_code == 403


def test_verify_whitelist_allowed():
    mock_decoded = {
        "uid": "test-uid",
        "email": "allowed@gmail.com",
        "name": "Test User",
    }
    with patch("app.middleware.auth.verify_id_token", return_value=mock_decoded), \
         patch("app.routers.auth.upsert_user_profile"), \
         patch.dict("os.environ", {"ALLOWED_EMAILS": "allowed@gmail.com,other@gmail.com"}):
            response = client.post(
                "/api/auth/verify",
                headers={"Authorization": "Bearer valid-token"},
            )
            assert response.status_code == 200
            assert response.json()["uid"] == "test-uid"
