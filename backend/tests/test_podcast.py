import asyncio
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.instructions import build_instructions
from app.routers import podcast as podcast_router


client = TestClient(app)

MOCK_USER = {
    "uid": "test-uid",
    "email": "test@example.com",
    "name": "Test User",
}


def _auth_patch():
    return patch("app.middleware.auth.verify_access_token", return_value=MOCK_USER)


def _db_context(row=None, rows=None):
    cursor = MagicMock()
    cursor.fetchone.return_value = row
    cursor.fetchall.return_value = rows or []
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = None

    conn = MagicMock()
    conn.cursor.return_value = cursor
    conn.__enter__.return_value = conn
    conn.__exit__.return_value = None
    return conn


def test_instructions_builder():
    memory = {
        "interests": "AI, 기술",
        "tone": "친근한",
        "depth": "중급",
        "custom": "예시를 많이 주세요",
        "feedbackHistory": [
            {"date": "2026-03-18", "rating": "bad"},
            {"date": "2026-03-19", "rating": "bad"},
            {"date": "2026-03-20", "rating": "bad"},
        ],
    }
    prompt = build_instructions(memory)
    assert "관심 분야: AI, 기술" in prompt
    assert "톤: 친근한" in prompt
    assert "더 흥미롭게 만들어주세요." in prompt


def test_window_cutoff_shape():
    start, end = podcast_router._window_cutoff("2026-03-19")
    assert end.strftime("%H:%M") == "06:40"
    assert start < end


def test_podcast_id():
    assert podcast_router._podcast_id("uid", "2026-03-19") == "uid-2026-03-19"


def test_generate_requires_scheduler_auth():
    response = client.post("/api/generate")
    assert response.status_code == 401


def test_generate_with_invalid_scheduler_email_is_rejected():
    with patch.dict(os.environ, {"CLOUD_RUN_URL": "https://podcast.test", "SCHEDULER_SERVICE_ACCOUNT": "expected@serviceaccount.com"}), \
         patch("app.middleware.auth.google_id_token.verify_oauth2_token", return_value={"email": "other@project"}):
        response = client.post("/api/generate", headers={"Authorization": "Bearer token"})
    assert response.status_code == 403


def test_generate_with_no_allowed_users_returns_no_users():
    with patch.dict(os.environ, {"ALLOWED_EMAILS": "", "CLOUD_RUN_URL": "https://podcast.test"}), \
         patch("app.middleware.auth.google_id_token.verify_oauth2_token", return_value={"email": "expected@serviceaccount.com"}):
        response = client.post("/api/generate", headers={"Authorization": "Bearer token"})
    assert response.status_code == 200
    assert response.json()["status"] == "no_users"


def test_generate_me_conflict_when_already_attempted_today():
    db_row = {"status": "failed"}
    with _auth_patch(), patch(
        "app.routers.podcast.get_db",
        return_value=_db_context(row=db_row),
    ):
        response = client.post("/api/generate/me", headers={"Authorization": "Bearer token"})
    assert response.status_code == 409
    assert response.json()["detail"] == "Immediate podcast generation is limited to once per day"


def test_generate_me_starts_background_generation():
    with _auth_patch(), patch(
        "app.routers.podcast.get_db",
        return_value=_db_context(row=None),
    ):
        response = client.post("/api/generate/me", headers={"Authorization": "Bearer token"})
    assert response.status_code == 200
    assert response.json()["status"] == "generating"


def test_get_today_podcast_none_for_missing_record():
    with _auth_patch(), patch("app.routers.podcast._fetch_podcast_record", return_value=None):
        response = client.get("/api/podcasts/today", headers={"Authorization": "Bearer token"})
    assert response.status_code == 200
    assert response.json()["podcast"] is None


def test_get_today_podcast_includes_signed_url_when_completed():
    record = {
        "id": "test-uid-2026-03-19",
        "user_id": "test-uid",
        "date": datetime.now(timezone(timedelta(hours=9))).date(),
        "status": "completed",
        "source_ids": ["a", "b"],
        "source_count": 2,
        "audio_path": "podcasts/test-uid/2026-03-19.mp3",
        "duration_seconds": 600,
        "generated_at": datetime.now(timezone.utc),
        "instructions_used": None,
        "error": None,
        "feedback": None,
        "downloaded": False,
    }
    with _auth_patch(), patch("app.routers.podcast._fetch_podcast_record", return_value=record), \
         patch("app.routers.podcast.create_podcast_audio_signed_url", return_value="https://signed-url"):
        response = client.get("/api/podcasts/today", headers={"Authorization": "Bearer token"})
    assert response.status_code == 200
    assert response.json()["podcast"]["audioUrl"] == "https://signed-url"


def test_mark_downloaded_not_found():
    with _auth_patch(), patch("app.routers.podcast.get_db", return_value=_db_context(row=None)):
        response = client.post("/api/podcasts/test-uid-2026-03-19/downloaded", headers={"Authorization": "Bearer token"})
    assert response.status_code == 404


def test_mark_downloaded_success():
    with _auth_patch(), patch("app.routers.podcast.get_db", return_value=_db_context(row={"id": "test-uid-2026-03-19"})):
        response = client.post("/api/podcasts/test-uid-2026-03-19/downloaded", headers={"Authorization": "Bearer token"})
    assert response.status_code == 200
    assert response.json() == {}


def test_submit_feedback_invalid_rating():
    with _auth_patch(), patch("app.routers.podcast.get_db", return_value=_db_context(row={"uid": "test-uid", "date": "2026-03-19"})):
        response = client.post(
            "/api/podcasts/test-uid-2026-03-19/feedback",
            headers={"Authorization": "Bearer token"},
            json={"rating": "excellent"},
        )
    assert response.status_code == 400


def test_submit_feedback_persists_memory():
    db_rows = {
        "podcast": {"uid": "test-uid", "date": "2026-03-19"},
        "memory": None,
    }

    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = None
    cursor.fetchone.side_effect = [
        db_rows["podcast"],
        None,
        None,
    ]
    cursor.fetchall.return_value = []
    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.__exit__.return_value = None
    conn.cursor.return_value = cursor

    def execute_side_effect(query, params=None):
        return None
    cursor.execute.side_effect = execute_side_effect

    with _auth_patch(), patch("app.routers.podcast.get_db", return_value=conn):
        response = client.post(
            "/api/podcasts/test-uid-2026-03-19/feedback",
            headers={"Authorization": "Bearer token"},
            json={"rating": "good"},
        )

    assert response.status_code == 200
    assert response.json()["podcastId"] == "test-uid-2026-03-19"


def test_generate_all_limits_concurrency():
    users = [{"uid": "a"}, {"uid": "b"}, {"uid": "c"}]
    with patch.dict(
        os.environ,
        {
            "ALLOWED_EMAILS": "a@x,b@x,c@x",
            "GENERATE_MAX_CONCURRENCY": "2",
            "CLOUD_RUN_URL": "https://podcast.test",
            "SCHEDULER_SERVICE_ACCOUNT": "scheduler@project.iam.gserviceaccount.com",
        },
    ), \
         patch("app.middleware.auth.google_id_token.verify_oauth2_token", return_value={"email": "scheduler@project.iam.gserviceaccount.com"}), \
         patch("app.routers.podcast.get_db", return_value=_db_context(rows=users)), \
         patch("app.routers.podcast._generate_for_user", new=AsyncMock(return_value={"status": "completed"})):
        response = client.post("/api/generate", headers={"Authorization": "Bearer scheduler"})
        assert response.status_code == 200


def test_generate_for_user_returns_no_sources():
    with patch("app.routers.podcast._fetch_podcast_record", return_value=None), \
         patch("app.routers.podcast._update_podcast_status", new=AsyncMock()), \
         patch("app.routers.podcast._get_sources_for_window", new=AsyncMock(return_value=[])), \
         patch("app.routers.podcast._notify_user"):
        result = asyncio.run(podcast_router._generate_for_user("test-uid", "2026-03-19"))

    assert result["reason"] == "no_sources"
    assert result["uid"] == "test-uid"


def test_generate_for_user_timeout_marks_failed():
    sources = [{"sourceId": "s1", "originalType": "application/pdf", "originalStoragePath": "a", "windowDate": "2026-03-19"}]
    fake_client = AsyncMock()
    fake_client.create_notebook.return_value = "nb-1"
    fake_client.add_source.return_value = None
    fake_client.generate_audio.side_effect = asyncio.TimeoutError()
    fake_client.delete_notebook.return_value = None
    fake_client.close.return_value = None

    with patch("app.routers.podcast._fetch_podcast_record", return_value={"status": "ready"}), \
         patch("app.routers.podcast._update_podcast_status", new=AsyncMock()), \
         patch("app.routers.podcast._get_sources_for_window", new=AsyncMock(return_value=sources)), \
         patch("app.routers.podcast._get_user_memory", new=AsyncMock(return_value=None)), \
         patch("app.routers.podcast.load_nb_session", new=AsyncMock(return_value={"storageState": {"cookies": []}})), \
         patch("app.routers.podcast._download_source_pdf", new=AsyncMock(return_value="/tmp/source.pdf")), \
         patch("app.routers.podcast.NotebookLMClient", return_value=fake_client):
        result = asyncio.run(podcast_router._generate_for_user("test-uid", "2026-03-19"))

    assert result["status"] == "failed"
    assert result["error"] == "audio_timeout"


def test_memory_no_auth():
    response = client.get("/api/memory")
    assert response.status_code == 401


def test_get_memory_defaults():
    with _auth_patch(), patch("app.routers.memory.get_db", return_value=_db_context(row=None)):
        response = client.get("/api/memory", headers={"Authorization": "Bearer token"})
    assert response.status_code == 200
    assert response.json() == {
        "interests": "",
        "tone": "",
        "depth": "",
        "custom": "",
        "feedbackHistory": [],
    }


def test_put_memory():
    rows = [
        {
            "interests": "AI",
            "tone": "차분한",
            "depth": "입문",
            "custom": "짧게",
            "feedback_history": [{"date": "2026-03-18", "rating": "good"}],
        }
    ]

    with _auth_patch(), patch("app.routers.memory.get_db", return_value=_db_context(row=rows[0])):
        response = client.put(
            "/api/memory",
            headers={"Authorization": "Bearer token"},
            json={"interests": "AI", "tone": "차분한", "depth": "입문", "custom": "짧게"},
        )
    assert response.status_code == 200
    assert response.json()["interests"] == "AI"
    assert response.json()["feedbackHistory"] == [{"date": "2026-03-18", "rating": "good"}]
