import sys
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from app.main import app
from app.services.storage import validate_file_content

client = TestClient(app)

MOCK_USER = {
    "uid": "test-uid",
    "email": "test@gmail.com",
    "name": "Test User",
}

AUTH_HEADERS = {"Authorization": "Bearer valid-token"}


def _auth_patch():
    return patch("app.middleware.auth.verify_id_token", return_value=MOCK_USER)


def _env_patch():
    return patch.dict("os.environ", {"ALLOWED_EMAILS": ""})


class TestUpload:
    def test_upload_no_auth(self):
        response = client.post("/api/sources/upload")
        assert response.status_code == 401

    def test_upload_invalid_mime(self):
        with _auth_patch(), _env_patch():
            response = client.post(
                "/api/sources/upload",
                headers=AUTH_HEADERS,
                files={"file": ("test.txt", b"hello", "text/plain")},
            )
            assert response.status_code == 400
            assert "Unsupported file type" in response.json()["detail"]

    def test_upload_empty_file(self):
        with _auth_patch(), _env_patch():
            response = client.post(
                "/api/sources/upload",
                headers=AUTH_HEADERS,
                files={"file": ("test.pdf", b"", "application/pdf")},
            )
            assert response.status_code == 400
            assert "Empty file" in response.json()["detail"]

    def test_upload_magic_bytes_mismatch(self):
        """File claims to be PDF but content is not."""
        with _auth_patch(), _env_patch():
            response = client.post(
                "/api/sources/upload",
                headers=AUTH_HEADERS,
                files={"file": ("fake.pdf", b"not a pdf at all", "application/pdf")},
            )
            assert response.status_code == 400
            assert "does not match" in response.json()["detail"]

    @patch("app.services.storage._get_bucket")
    @patch("app.services.storage.get_firestore_client")
    def test_upload_pdf_success(self, mock_db, mock_bucket):
        mock_blob = MagicMock()
        mock_bucket.return_value.blob.return_value = mock_blob
        mock_collection = MagicMock()
        mock_db.return_value.collection.return_value = mock_collection
        mock_doc_ref = MagicMock()
        mock_collection.document.return_value = mock_doc_ref

        pdf_content = b"%PDF-1.4 test content"

        with _auth_patch(), _env_patch():
            response = client.post(
                "/api/sources/upload",
                headers=AUTH_HEADERS,
                files={"file": ("test.pdf", pdf_content, "application/pdf")},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["fileName"] == "test.pdf"
        assert data["originalType"] == "application/pdf"
        assert data["originalStoragePath"] is not None
        assert data["convertedStoragePath"] is None
        assert data["status"] == "uploaded"
        mock_blob.upload_from_string.assert_called_once()
        mock_doc_ref.set.assert_called_once()

    @patch("app.services.storage._get_bucket")
    @patch("app.services.storage.get_firestore_client")
    def test_upload_image_converts_to_pdf(self, mock_db, mock_bucket):
        mock_blob = MagicMock()
        mock_bucket.return_value.blob.return_value = mock_blob
        mock_collection = MagicMock()
        mock_db.return_value.collection.return_value = mock_collection
        mock_doc_ref = MagicMock()
        mock_collection.document.return_value = mock_doc_ref

        mock_img2pdf = MagicMock()
        mock_img2pdf.convert.return_value = b"%PDF converted"

        # Minimal valid PNG
        png_content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

        with _auth_patch(), _env_patch(), patch.dict(sys.modules, {"img2pdf": mock_img2pdf}):
            response = client.post(
                "/api/sources/upload",
                headers=AUTH_HEADERS,
                files={"file": ("screenshot.png", png_content, "image/png")},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["originalType"] == "image/png"
        assert data["convertedType"] == "application/pdf"
        assert data["convertedStoragePath"] is not None
        assert data["originalStoragePath"] is not None
        assert data["status"] == "ready"
        mock_img2pdf.convert.assert_called_once()


class TestValidateFileContent:
    def test_valid_pdf(self):
        assert validate_file_content(b"%PDF-1.4 content", "application/pdf") is True

    def test_invalid_pdf(self):
        assert validate_file_content(b"not a pdf", "application/pdf") is False

    def test_valid_png(self):
        assert validate_file_content(b"\x89PNG\r\n\x1a\n" + b"\x00" * 10, "image/png") is True

    def test_invalid_png(self):
        assert validate_file_content(b"\x00\x00\x00\x00", "image/png") is False

    def test_valid_jpeg(self):
        assert validate_file_content(b"\xff\xd8\xff\xe0", "image/jpeg") is True

    def test_invalid_jpeg(self):
        assert validate_file_content(b"\x00\x00\x00", "image/jpeg") is False

    def test_valid_webp(self):
        assert validate_file_content(b"RIFF\x00\x00\x00\x00WEBP", "image/webp") is True

    def test_invalid_webp_no_webp_marker(self):
        assert validate_file_content(b"RIFF\x00\x00\x00\x00NOPE", "image/webp") is False

    def test_unknown_type(self):
        assert validate_file_content(b"anything", "text/plain") is False


class TestListSources:
    def test_list_no_auth(self):
        response = client.get("/api/sources")
        assert response.status_code == 401

    @patch("app.services.storage.get_firestore_client")
    def test_list_sources(self, mock_db):
        mock_query = MagicMock()
        mock_collection = MagicMock()
        mock_db.return_value.collection.return_value = mock_collection
        mock_collection.where.return_value = mock_collection
        mock_collection.order_by.return_value = mock_query
        mock_query.stream.return_value = []

        with _auth_patch(), _env_patch():
            response = client.get(
                "/api/sources?date=2026-03-19",
                headers=AUTH_HEADERS,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["date"] == "2026-03-19"
        assert data["sources"] == []

    def test_list_invalid_date(self):
        with _auth_patch(), _env_patch():
            response = client.get(
                "/api/sources?date=invalid",
                headers=AUTH_HEADERS,
            )
            assert response.status_code == 400


class TestDeleteSource:
    def test_delete_no_auth(self):
        response = client.delete("/api/sources/abc123")
        assert response.status_code == 401

    @patch("app.services.storage._get_bucket")
    @patch("app.services.storage.get_firestore_client")
    def test_delete_not_found(self, mock_db, mock_bucket):
        mock_doc_ref = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = False
        mock_doc_ref.get.return_value = mock_doc
        mock_db.return_value.collection.return_value.document.return_value = mock_doc_ref

        with _auth_patch(), _env_patch():
            response = client.delete(
                "/api/sources/nonexistent",
                headers=AUTH_HEADERS,
            )
            assert response.status_code == 404

    @patch("app.services.storage._get_bucket")
    @patch("app.services.storage.get_firestore_client")
    def test_delete_wrong_user(self, mock_db, mock_bucket):
        mock_doc_ref = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {"uid": "other-uid"}
        mock_doc_ref.get.return_value = mock_doc
        mock_db.return_value.collection.return_value.document.return_value = mock_doc_ref

        with _auth_patch(), _env_patch():
            response = client.delete(
                "/api/sources/abc123",
                headers=AUTH_HEADERS,
            )
            assert response.status_code == 404

    @patch("app.services.storage._get_bucket")
    @patch("app.services.storage.get_firestore_client")
    def test_delete_success(self, mock_db, mock_bucket):
        mock_doc_ref = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {
            "uid": "test-uid",
            "originalStoragePath": "sources/test-uid/2026-03-19/abc.png",
            "convertedStoragePath": "sources/test-uid/2026-03-19/abc.pdf",
            "originalType": "image/png",
        }
        mock_doc_ref.get.return_value = mock_doc
        mock_db.return_value.collection.return_value.document.return_value = mock_doc_ref

        mock_blob = MagicMock()
        mock_blob.exists.return_value = True
        mock_bucket.return_value.blob.return_value = mock_blob

        with _auth_patch(), _env_patch():
            response = client.delete(
                "/api/sources/abc123",
                headers=AUTH_HEADERS,
            )

        assert response.status_code == 200
        assert response.json()["deleted"] is True
        # Both original and converted blobs should be deleted
        assert mock_blob.delete.call_count == 2
        mock_doc_ref.delete.assert_called_once()

    @patch("app.services.storage._get_bucket")
    @patch("app.services.storage.get_firestore_client")
    def test_delete_pdf_only_one_blob(self, mock_db, mock_bucket):
        """PDF-only source has no convertedStoragePath."""
        mock_doc_ref = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {
            "uid": "test-uid",
            "originalStoragePath": "sources/test-uid/2026-03-19/abc.pdf",
            "convertedStoragePath": None,
            "originalType": "application/pdf",
        }
        mock_doc_ref.get.return_value = mock_doc
        mock_db.return_value.collection.return_value.document.return_value = mock_doc_ref

        mock_blob = MagicMock()
        mock_blob.exists.return_value = True
        mock_bucket.return_value.blob.return_value = mock_blob

        with _auth_patch(), _env_patch():
            response = client.delete(
                "/api/sources/abc123",
                headers=AUTH_HEADERS,
            )

        assert response.status_code == 200
        # Only original blob deleted (convertedStoragePath is None)
        assert mock_blob.delete.call_count == 1
        mock_doc_ref.delete.assert_called_once()
