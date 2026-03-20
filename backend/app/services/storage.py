from __future__ import annotations

import io
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from PIL import Image

from app.services.db import get_db, serialize_date, serialize_timestamp, utc_now

KST = timezone(timedelta(hours=9))
logger = logging.getLogger(__name__)

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/webp",
}

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB

_MAGIC_SIGNATURES: dict[str, list[bytes]] = {
    "application/pdf": [b"%PDF"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/webp": [b"RIFF"],
}


def _normalize_env_value(value: str) -> str:
    return value.strip().replace("\r", "").replace("\n", "").strip("'\"")


def _supabase_url() -> str:
    value = _normalize_env_value(os.getenv("SUPABASE_URL", ""))
    if not value:
        raise RuntimeError("SUPABASE_URL not configured")
    return value


def _service_role_key() -> str:
    value = _normalize_env_value(os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""))
    if not value:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY not configured")
    return value


def _storage_base_url() -> str:
    return f"{_supabase_url().rstrip('/')}/storage/v1"


def _storage_headers() -> dict[str, str]:
    key = _service_role_key()
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
    }


def _today_date_str() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def _sources_bucket() -> str:
    return _normalize_env_value(os.getenv("SUPABASE_STORAGE_BUCKET_SOURCES", "sources")) or "sources"


def _podcasts_bucket() -> str:
    return _normalize_env_value(os.getenv("SUPABASE_STORAGE_BUCKET_PODCASTS", "podcasts")) or "podcasts"


def _read_bytes(source: bytes | str | os.PathLike[str]) -> bytes:
    if isinstance(source, (str, os.PathLike)):
        with open(os.fspath(source), "rb") as handle:
            return handle.read()
    return source


def validate_file_content(file_bytes: bytes, content_type: str) -> bool:
    sigs = _MAGIC_SIGNATURES.get(content_type)
    if not sigs:
        return False
    for sig in sigs:
        if file_bytes[:len(sig)] == sig:
            if content_type == "image/webp":
                return len(file_bytes) >= 12 and file_bytes[8:12] == b"WEBP"
            return True
    return False


def _image_to_pdf_bytes(payload: bytes) -> bytes:
    with Image.open(io.BytesIO(payload)) as image:
        image.load()
        prepared = image
        should_close_prepared = False

        has_alpha = image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info)
        if has_alpha:
            rgba_image = image.convert("RGBA")
            background = Image.new("RGB", rgba_image.size, (255, 255, 255))
            background.paste(rgba_image, mask=rgba_image.getchannel("A"))
            prepared = background
            rgba_image.close()
            should_close_prepared = True
        elif image.mode != "RGB":
            prepared = image.convert("RGB")
            should_close_prepared = True

        try:
            buffer = io.BytesIO()
            prepared.save(buffer, format="PDF", resolution=100.0)
            return buffer.getvalue()
        finally:
            if should_close_prepared:
                prepared.close()


def upload_bytes(bucket: str, path: str, payload: bytes, *, content_type: str) -> None:
    filename = path.rsplit("/", 1)[-1]
    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            f"{_storage_base_url()}/object/{bucket}/{path}",
            headers={
                **_storage_headers(),
                "x-upsert": "true",
            },
            files={"file": (filename, payload, content_type)},
        )
        response.raise_for_status()


def download_bytes(bucket: str, path: str) -> bytes:
    with httpx.Client(timeout=30.0) as client:
        response = client.get(
            f"{_storage_base_url()}/object/{bucket}/{path}",
            headers=_storage_headers(),
        )
        response.raise_for_status()
        return response.content


def delete_paths(bucket: str, paths: list[str]) -> None:
    non_empty = [path for path in paths if path]
    if non_empty:
        with httpx.Client(timeout=30.0) as client:
            response = client.delete(
                f"{_storage_base_url()}/object/{bucket}",
                headers=_storage_headers(),
                json={"prefixes": non_empty},
            )
            response.raise_for_status()


async def upload_source(uid: str, source: bytes | str | os.PathLike[str], filename: str, content_type: str) -> dict[str, Any]:
    source_id = uuid.uuid4().hex[:12]
    date_str = _today_date_str()
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    storage_path = f"sources/{uid}/{date_str}/{source_id}.{ext}"

    upload_bytes(_sources_bucket(), storage_path, _read_bytes(source), content_type=content_type)

    uploaded_at = utc_now()
    with get_db() as conn, conn.cursor() as cur:
        cur.execute(
            """
            insert into profiles (id)
            values (%s)
            on conflict (id) do nothing
            """,
            (uid,),
        )
        cur.execute(
            """
            insert into sources (
                id,
                user_id,
                file_name,
                original_type,
                converted_type,
                original_storage_path,
                converted_storage_path,
                uploaded_at,
                window_date,
                status
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s::date, %s)
            """,
            (
                source_id,
                uid,
                filename,
                content_type,
                None,
                storage_path,
                None,
                uploaded_at,
                date_str,
                "uploaded",
            ),
        )

    return {
        "sourceId": source_id,
        "uid": uid,
        "fileName": filename,
        "originalType": content_type,
        "convertedType": None,
        "originalStoragePath": storage_path,
        "convertedStoragePath": None,
        "uploadedAt": uploaded_at.isoformat(),
        "windowDate": date_str,
        "status": "uploaded",
    }


async def convert_image_to_pdf(
    uid: str,
    source_id: str,
    image_source: bytes | str | os.PathLike[str],
    original_storage_path: str,
) -> str:
    pdf_bytes = _image_to_pdf_bytes(_read_bytes(image_source))
    pdf_path = original_storage_path.rsplit(".", 1)[0] + ".pdf"

    upload_bytes(_sources_bucket(), pdf_path, pdf_bytes, content_type="application/pdf")

    with get_db() as conn, conn.cursor() as cur:
        cur.execute(
            """
            update sources
            set converted_type = %s,
                converted_storage_path = %s,
                status = %s
            where id = %s and user_id = %s
            """,
            ("application/pdf", pdf_path, "ready", source_id, uid),
        )

    return pdf_path


async def list_sources(uid: str, date: str) -> list[dict[str, Any]]:
    with get_db() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select
                id,
                file_name,
                original_type,
                converted_type,
                original_storage_path,
                converted_storage_path,
                uploaded_at,
                window_date,
                status
            from sources
            where user_id = %s
              and window_date = %s::date
              and status = any(%s)
            order by uploaded_at asc
            """,
            (uid, date, ["uploaded", "processing", "ready", "used"]),
        )
        rows = cur.fetchall()

    return [
        {
            "sourceId": row["id"],
            "fileName": row["file_name"],
            "originalType": row["original_type"],
            "convertedType": row["converted_type"],
            "originalStoragePath": row["original_storage_path"],
            "convertedStoragePath": row["converted_storage_path"],
            "uploadedAt": serialize_timestamp(row["uploaded_at"]),
            "windowDate": serialize_date(row["window_date"]),
            "status": row["status"],
        }
        for row in rows
    ]


async def delete_source(uid: str, source_id: str) -> bool:
    with get_db() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select original_storage_path, converted_storage_path
            from sources
            where id = %s and user_id = %s
            """,
            (source_id, uid),
        )
        row = cur.fetchone()
        if not row:
            return False

        cur.execute("delete from sources where id = %s and user_id = %s", (source_id, uid))

    try:
        delete_paths(
            _sources_bucket(),
            [row["original_storage_path"], row["converted_storage_path"]],
        )
    except Exception:
        logger.exception("Source storage cleanup failed for %s", source_id)

    return True


def upload_podcast_audio(audio_path: str, payload: bytes) -> None:
    upload_bytes(_podcasts_bucket(), audio_path, payload, content_type="audio/mpeg")


def download_podcast_audio(audio_path: str) -> bytes:
    return download_bytes(_podcasts_bucket(), audio_path)


def delete_podcast_audio(audio_path: str) -> None:
    delete_paths(_podcasts_bucket(), [audio_path])


def create_podcast_audio_signed_url(audio_path: str, *, expires_in: int = 60 * 60 * 6) -> str:
    result = _storage_client().storage.from_(_podcasts_bucket()).create_signed_url(audio_path, expires_in)
    if isinstance(result, str):
        return result

    signed_url = (
        result.get("signedURL")
        or result.get("signedUrl")
        or result.get("signed_url")
    )
    if not signed_url:
        raise RuntimeError("Failed to create signed podcast URL")

    if signed_url.startswith("http://") or signed_url.startswith("https://"):
        return signed_url

    return f"{_supabase_url().rstrip('/')}/storage/v1{signed_url if signed_url.startswith('/') else '/' + signed_url}"
