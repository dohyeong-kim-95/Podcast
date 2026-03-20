import asyncio
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import UploadFile
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.routers.sources import _spill_upload_to_tempfile
from app.services.storage import delete_source, validate_file_content, _image_to_pdf_bytes


client = TestClient(app)


MOCK_USER = {
    "uid": "test-uid",
    "email": "test@example.com",
    "name": "Test User",
}


def _auth_patch():
    return patch("app.middleware.auth.verify_access_token", return_value=MOCK_USER)


def test_upload_rejects_empty_file():
    with _auth_patch(), patch("app.routers.sources.upload_source", new=AsyncMock()):
        response = client.post(
            "/api/sources/upload",
            headers={"Authorization": "Bearer valid-token"},
            files={"file": ("test.pdf", b"", "application/pdf")},
        )
    assert response.status_code == 400
    assert response.json()["detail"] == "Empty file"


def test_upload_rejects_invalid_mime():
    with _auth_patch():
        response = client.post(
            "/api/sources/upload",
            headers={"Authorization": "Bearer valid-token"},
            files={"file": ("test.txt", b"hello", "text/plain")},
        )
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_spill_upload_to_tempfile_enforces_max_size():
    upload = UploadFile(filename="large.pdf", file=BytesIO(b"%PDF-1.4" * 1024 * 1024))
    with patch("app.routers.sources.MAX_FILE_SIZE", 10):
        try:
            asyncio.run(_spill_upload_to_tempfile(upload))
            assert False, "Expected HTTPException"
        except Exception as exc:  # pragma: no cover - validates API-level exception class contract
            assert "File size exceeds" in str(exc)


def test_upload_pdf_success():
    expected = {
        "sourceId": "src-1",
        "uid": "test-uid",
        "fileName": "test.pdf",
        "originalType": "application/pdf",
        "convertedType": None,
        "originalStoragePath": "sources/test-uid/2026-01-01/test.pdf",
        "convertedStoragePath": None,
        "uploadedAt": "2026-01-01T00:00:00+09:00",
        "windowDate": "2026-01-01",
        "status": "uploaded",
    }
    with _auth_patch(), patch(
        "app.routers.sources.upload_source",
        new=AsyncMock(return_value=expected),
    ):
        response = client.post(
            "/api/sources/upload",
            headers={"Authorization": "Bearer valid-token"},
            files={"file": ("test.pdf", b"%PDF-1.4 sample", "application/pdf")},
        )

    assert response.status_code == 200
    assert response.json() == expected


def test_upload_image_converts_to_pdf():
    source_payload = {
        "sourceId": "src-1",
        "uid": "test-uid",
        "fileName": "img.png",
        "originalType": "image/png",
        "convertedType": None,
        "originalStoragePath": "sources/test-uid/2026-01-01/img.png",
        "convertedStoragePath": None,
        "uploadedAt": "2026-01-01T00:00:00+09:00",
        "windowDate": "2026-01-01",
        "status": "uploaded",
    }

    with _auth_patch(), \
         patch("app.routers.sources.upload_source", new=AsyncMock(return_value=source_payload)), \
         patch("app.routers.sources.convert_image_to_pdf", new=AsyncMock(return_value="sources/test-uid/2026-01-01/img.png.pdf")):
        response = client.post(
            "/api/sources/upload",
            headers={"Authorization": "Bearer valid-token"},
            files={"file": ("img.png", b"\x89PNG\r\n\x1a\nbytes", "image/png")},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["convertedType"] == "application/pdf"
    assert payload["convertedStoragePath"].endswith(".pdf")


def test_list_sources():
    rows = [
        {
            "sourceId": "s1",
            "fileName": "a.pdf",
            "originalType": "application/pdf",
            "convertedType": "application/pdf",
            "originalStoragePath": "a",
            "convertedStoragePath": "a.pdf",
            "uploadedAt": "2026-01-01T00:00:00+09:00",
            "windowDate": "2026-01-01",
            "status": "ready",
        },
    ]
    with _auth_patch(), patch("app.routers.sources.list_sources", new=AsyncMock(return_value=rows)):
        response = client.get(
            "/api/sources?date=2026-01-01",
            headers={"Authorization": "Bearer valid-token"},
        )

    assert response.status_code == 200
    assert response.json() == {"date": "2026-01-01", "sources": rows}


def test_list_sources_rejects_invalid_date():
    with _auth_patch(), patch("app.routers.sources.list_sources", new=AsyncMock(return_value=[])):
        response = client.get(
            "/api/sources?date=invalid",
            headers={"Authorization": "Bearer valid-token"},
        )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid date format. Use YYYY-MM-DD"


def test_delete_source_not_found():
    with _auth_patch(), patch("app.routers.sources.delete_source", new=AsyncMock(return_value=False)):
        response = client.delete("/api/sources/unknown", headers={"Authorization": "Bearer valid-token"})
    assert response.status_code == 404


def test_delete_source_success():
    with _auth_patch(), patch("app.routers.sources.delete_source", new=AsyncMock(return_value=True)):
        response = client.delete("/api/sources/src-1", headers={"Authorization": "Bearer valid-token"})
    assert response.status_code == 200
    assert response.json() == {"deleted": True, "sourceId": "src-1"}


def test_delete_source_keeps_db_delete_when_storage_cleanup_fails():
    cursor = MagicMock()
    cursor.fetchone.return_value = {
        "original_storage_path": "sources/test-uid/2026-01-01/img.png",
        "converted_storage_path": None,
    }
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = None
    conn = MagicMock()
    conn.cursor.return_value = cursor
    conn.__enter__.return_value = conn
    conn.__exit__.return_value = None

    with patch("app.services.storage.get_db", return_value=conn), \
         patch("app.services.storage.delete_paths", side_effect=RuntimeError("storage unavailable")):
        deleted = asyncio.run(delete_source("test-uid", "src-1"))

    assert deleted is True
    cursor.execute.assert_any_call("delete from sources where id = %s and user_id = %s", ("src-1", "test-uid"))


class TestValidateFileContent:
    def test_valid_pdf(self):
        assert validate_file_content(b"%PDF-1.4", "application/pdf") is True

    def test_invalid_pdf(self):
        assert validate_file_content(b"not pdf", "application/pdf") is False

    def test_valid_png(self):
        assert validate_file_content(b"\x89PNG\r\n\x1a\n" + b"\x00" * 5, "image/png") is True

    def test_invalid_png(self):
        assert validate_file_content(b"\x00\x00\x00\x00", "image/png") is False

    def test_valid_webp(self):
        assert validate_file_content(b"RIFF\x00\x00\x00\x00WEBP", "image/webp") is True

    def test_invalid_webp(self):
        assert validate_file_content(b"RIFF\x00\x00\x00\x00xxxx", "image/webp") is False


def test_image_to_pdf_bytes_handles_transparent_png():
    image = Image.new("RGBA", (4, 4), (255, 0, 0, 128))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    image.close()

    payload = _image_to_pdf_bytes(buffer.getvalue())

    assert payload.startswith(b"%PDF")
