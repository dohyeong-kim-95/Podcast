"""T-032-2: Podcast generation pipeline tests."""

import os
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.instructions import build_instructions

client = TestClient(app)

MOCK_USER = {
    "uid": "test-uid",
    "email": "test@gmail.com",
    "name": "Test User",
}

AUTH_HEADERS = {"Authorization": "Bearer valid-token"}

# Patch targets: must match import location in each module
_DB_PATCH = "app.routers.podcast.get_firestore_client"
_STORAGE_PATCH = "app.routers.podcast.storage"


def _auth_patch():
    return patch("app.middleware.auth.verify_id_token", return_value=MOCK_USER)


def _env_patch():
    return patch.dict("os.environ", {"ALLOWED_EMAILS": ""})


def _scheduler_patch(email="scheduler@project.iam.gserviceaccount.com"):
    mock_claims = {"email": email, "aud": "https://podcast-test.run.app"}
    return patch(
        "app.middleware.auth.google_id_token.verify_oauth2_token",
        return_value=mock_claims,
    )


def _scheduler_env():
    return patch.dict("os.environ", {
        "CLOUD_RUN_URL": "https://podcast-test.run.app",
        "SCHEDULER_SERVICE_ACCOUNT": "scheduler@project.iam.gserviceaccount.com",
        "ALLOWED_EMAILS": "test@gmail.com",
    })


# ─── T-031: Instructions Builder Tests ────────────────────────


class TestBuildInstructions:
    def test_empty_memory(self):
        result = build_instructions(None)
        assert "한국어로 진행해주세요." in result
        assert "10분 분량으로 만들어주세요." in result

    def test_empty_dict(self):
        result = build_instructions({})
        lines = result.strip().split("\n")
        assert len(lines) == 2

    def test_with_interests(self):
        memory = {"interests": "AI, 기술"}
        result = build_instructions(memory)
        assert "관심 분야: AI, 기술" in result

    def test_with_tone(self):
        memory = {"preferredTone": "친근한"}
        result = build_instructions(memory)
        assert "톤: 친근한" in result

    def test_with_depth(self):
        memory = {"preferredDepth": "깊이있게"}
        result = build_instructions(memory)
        assert "깊이: 깊이있게" in result

    def test_with_custom_instructions(self):
        memory = {"customInstructions": "예시를 많이 들어주세요"}
        result = build_instructions(memory)
        assert "예시를 많이 들어주세요" in result

    def test_full_memory(self):
        memory = {
            "interests": "AI, 과학",
            "preferredTone": "유머러스한",
            "preferredDepth": "중급",
            "customInstructions": "전문 용어 설명 포함",
        }
        result = build_instructions(memory)
        assert "관심 분야: AI, 과학" in result
        assert "톤: 유머러스한" in result
        assert "깊이: 중급" in result
        assert "전문 용어 설명 포함" in result

    def test_feedback_signal_under_threshold(self):
        memory = {
            "feedbackHistory": [
                {"date": "2026-03-01", "rating": "bad"},
                {"date": "2026-03-02", "rating": "bad"},
                {"date": "2026-03-03", "rating": "good"},
            ]
        }
        result = build_instructions(memory)
        assert "더 흥미롭게 만들어주세요." not in result

    def test_feedback_signal_at_threshold(self):
        memory = {
            "feedbackHistory": [
                {"date": "2026-03-01", "rating": "bad"},
                {"date": "2026-03-02", "rating": "bad"},
                {"date": "2026-03-03", "rating": "bad"},
            ]
        }
        result = build_instructions(memory)
        assert "더 흥미롭게 만들어주세요." in result

    def test_feedback_signal_only_last_10(self):
        """Only the last 10 feedback entries should be considered."""
        old_bad = [{"date": f"2026-02-{i:02d}", "rating": "bad"} for i in range(1, 6)]
        recent_good = [{"date": f"2026-03-{i:02d}", "rating": "good"} for i in range(1, 11)]
        memory = {"feedbackHistory": old_bad + recent_good}
        result = build_instructions(memory)
        assert "더 흥미롭게 만들어주세요." not in result


# ─── T-032-1: Scheduler Token Validation Tests ────────────────


class TestSchedulerTokenValidation:
    def test_scheduler_no_auth(self):
        response = client.post("/api/generate")
        assert response.status_code == 401

    def test_scheduler_missing_cloud_run_url(self):
        with patch.dict("os.environ", {"CLOUD_RUN_URL": ""}):
            response = client.post(
                "/api/generate",
                headers=AUTH_HEADERS,
            )
            assert response.status_code == 500

    def test_scheduler_invalid_oidc(self):
        with patch.dict("os.environ", {"CLOUD_RUN_URL": "https://test.run.app"}):
            with patch(
                "app.middleware.auth.google_id_token.verify_oauth2_token",
                side_effect=Exception("Invalid"),
            ):
                response = client.post(
                    "/api/generate",
                    headers=AUTH_HEADERS,
                )
                assert response.status_code == 401

    def test_scheduler_wrong_service_account(self):
        """Token from unauthorized service account should be rejected."""
        wrong_claims = {"email": "wrong@project.iam.gserviceaccount.com"}
        with patch.dict("os.environ", {
            "CLOUD_RUN_URL": "https://test.run.app",
            "SCHEDULER_SERVICE_ACCOUNT": "correct@project.iam.gserviceaccount.com",
        }):
            with patch(
                "app.middleware.auth.google_id_token.verify_oauth2_token",
                return_value=wrong_claims,
            ):
                response = client.post(
                    "/api/generate",
                    headers=AUTH_HEADERS,
                )
                assert response.status_code == 403
                assert "Unauthorized service account" in response.json()["detail"]

    @patch(_DB_PATCH)
    def test_scheduler_valid_service_account(self, mock_db):
        """Valid service account token should be accepted."""
        mock_collection = MagicMock()
        mock_db.return_value.collection.return_value = mock_collection
        mock_collection.where.return_value = mock_collection
        mock_collection.limit.return_value = mock_collection
        mock_collection.stream.return_value = []

        with _scheduler_env(), _scheduler_patch():
            response = client.post(
                "/api/generate",
                headers=AUTH_HEADERS,
            )
            assert response.status_code == 200


# ─── T-032: Podcast Pipeline Tests ────────────────────────────


class TestGenerateMe:
    def test_no_auth(self):
        response = client.post("/api/generate/me")
        assert response.status_code == 401

    @patch(_DB_PATCH)
    def test_already_completed(self, mock_db):
        """If today's podcast is already completed, return 409."""
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {"status": "completed"}
        mock_db.return_value.collection.return_value.document.return_value.get.return_value = mock_doc

        with _auth_patch(), _env_patch():
            response = client.post(
                "/api/generate/me",
                headers=AUTH_HEADERS,
            )
            assert response.status_code == 409

    @patch(_DB_PATCH)
    def test_already_generating(self, mock_db):
        """If today's podcast is generating, return 409."""
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {"status": "generating"}
        mock_db.return_value.collection.return_value.document.return_value.get.return_value = mock_doc

        with _auth_patch(), _env_patch():
            response = client.post(
                "/api/generate/me",
                headers=AUTH_HEADERS,
            )
            assert response.status_code == 409

    @patch(_DB_PATCH)
    def test_trigger_generation(self, mock_db):
        """Should accept and start generation if no existing podcast."""
        mock_doc = MagicMock()
        mock_doc.exists = False
        mock_db.return_value.collection.return_value.document.return_value.get.return_value = mock_doc

        with _auth_patch(), _env_patch():
            response = client.post(
                "/api/generate/me",
                headers=AUTH_HEADERS,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "generating"

    @patch(_DB_PATCH)
    def test_retry_after_failure(self, mock_db):
        """Failed podcast should allow re-triggering."""
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {"status": "failed"}
        mock_db.return_value.collection.return_value.document.return_value.get.return_value = mock_doc

        with _auth_patch(), _env_patch():
            response = client.post(
                "/api/generate/me",
                headers=AUTH_HEADERS,
            )
            assert response.status_code == 200
            assert response.json()["status"] == "generating"


class TestGetTodayPodcast:
    def test_no_auth(self):
        response = client.get("/api/podcasts/today")
        assert response.status_code == 401

    @patch(_DB_PATCH)
    def test_no_podcast(self, mock_db):
        mock_doc = MagicMock()
        mock_doc.exists = False
        mock_db.return_value.collection.return_value.document.return_value.get.return_value = mock_doc

        with _auth_patch(), _env_patch():
            response = client.get(
                "/api/podcasts/today",
                headers=AUTH_HEADERS,
            )
            assert response.status_code == 200
            assert response.json()["podcast"] is None

    @patch(_STORAGE_PATCH)
    @patch(_DB_PATCH)
    def test_completed_podcast(self, mock_db, mock_storage):
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.id = "test-uid-2026-03-19"
        mock_doc.to_dict.return_value = {
            "uid": "test-uid",
            "date": "2026-03-19",
            "status": "completed",
            "audioPath": "podcasts/test-uid/2026-03-19.mp3",
            "sourceCount": 2,
            "durationSeconds": 600,
        }
        mock_db.return_value.collection.return_value.document.return_value.get.return_value = mock_doc

        mock_blob = MagicMock()
        mock_blob.exists.return_value = True
        mock_blob.generate_signed_url.return_value = "https://storage.example.com/signed"
        mock_storage.bucket.return_value.blob.return_value = mock_blob

        with _auth_patch(), _env_patch():
            response = client.get(
                "/api/podcasts/today",
                headers=AUTH_HEADERS,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["podcast"]["status"] == "completed"
            assert "audioUrl" in data["podcast"]


class TestFeedback:
    def test_no_auth(self):
        response = client.post("/api/podcasts/test-id/feedback")
        assert response.status_code == 401

    @patch(_DB_PATCH)
    def test_invalid_rating(self, mock_db):
        with _auth_patch(), _env_patch():
            response = client.post(
                "/api/podcasts/test-id/feedback",
                headers=AUTH_HEADERS,
                json={"rating": "excellent"},
            )
            assert response.status_code == 400

    @patch(_DB_PATCH)
    def test_not_found(self, mock_db):
        mock_doc = MagicMock()
        mock_doc.exists = False
        mock_db.return_value.collection.return_value.document.return_value.get.return_value = mock_doc

        with _auth_patch(), _env_patch():
            response = client.post(
                "/api/podcasts/test-id/feedback",
                headers=AUTH_HEADERS,
                json={"rating": "good"},
            )
            assert response.status_code == 404

    @patch(_DB_PATCH)
    def test_wrong_user(self, mock_db):
        mock_doc_ref = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {"uid": "other-uid", "date": "2026-03-19"}
        mock_doc_ref.get.return_value = mock_doc
        mock_db.return_value.collection.return_value.document.return_value = mock_doc_ref

        with _auth_patch(), _env_patch():
            response = client.post(
                "/api/podcasts/test-id/feedback",
                headers=AUTH_HEADERS,
                json={"rating": "good"},
            )
            assert response.status_code == 404

    @patch(_DB_PATCH)
    def test_submit_feedback_success(self, mock_db):
        mock_podcast_ref = MagicMock()
        mock_podcast_doc = MagicMock()
        mock_podcast_doc.exists = True
        mock_podcast_doc.to_dict.return_value = {"uid": "test-uid", "date": "2026-03-19"}
        mock_podcast_ref.get.return_value = mock_podcast_doc

        mock_user_ref = MagicMock()
        mock_user_doc = MagicMock()
        mock_user_doc.exists = True
        mock_user_doc.to_dict.return_value = {"memory": {"feedbackHistory": []}}
        mock_user_ref.get.return_value = mock_user_doc

        def mock_document(doc_id):
            if doc_id == "test-id":
                return mock_podcast_ref
            if doc_id == "test-uid":
                return mock_user_ref
            return MagicMock()

        mock_collection = MagicMock()
        mock_collection.document.side_effect = mock_document
        mock_db.return_value.collection.return_value = mock_collection

        with _auth_patch(), _env_patch():
            response = client.post(
                "/api/podcasts/test-id/feedback",
                headers=AUTH_HEADERS,
                json={"rating": "good"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["feedback"] == "good"
            mock_podcast_ref.update.assert_called_once_with({"feedback": "good"})


# ─── Source Window Tests ──────────────────────────────────────


class TestWindowLogic:
    def test_window_cutoff(self):
        from app.routers.podcast import _window_cutoff
        start, end = _window_cutoff("2026-03-19")
        assert end.hour == 6
        assert end.minute == 40
        assert end.day == 19
        assert start.day == 18
        assert start.hour == 6
        assert start.minute == 40

    def test_podcast_id_format(self):
        from app.routers.podcast import _podcast_id
        assert _podcast_id("user123", "2026-03-19") == "user123-2026-03-19"
