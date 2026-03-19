from datetime import datetime, timezone, timedelta
import os
import tempfile

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query

from app.middleware.auth import get_current_user
from app.services.storage import (
    ALLOWED_MIME_TYPES,
    MAX_FILE_SIZE,
    upload_source,
    convert_image_to_pdf,
    list_sources,
    delete_source,
    validate_file_content,
)

router = APIRouter(prefix="/api/sources", tags=["sources"])

KST = timezone(timedelta(hours=9))
UPLOAD_CHUNK_SIZE = 1024 * 1024
MAGIC_BYTE_PEEK = 12


async def _spill_upload_to_tempfile(file: UploadFile) -> tuple[str, bytes, int]:
    """Copy upload content to a temp file while enforcing the size limit incrementally."""
    total_size = 0
    header = bytearray()
    tmp = tempfile.NamedTemporaryFile(delete=False)

    try:
        while True:
            chunk = await file.read(UPLOAD_CHUNK_SIZE)
            if not chunk:
                break

            total_size += len(chunk)
            if total_size > MAX_FILE_SIZE:
                raise HTTPException(status_code=400, detail="File size exceeds 20MB limit")

            remaining_header = MAGIC_BYTE_PEEK - len(header)
            if remaining_header > 0:
                header.extend(chunk[:remaining_header])

            tmp.write(chunk)
    except Exception:
        tmp.close()
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise

    tmp.close()
    return tmp.name, bytes(header), total_size


@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """Upload a source file (PDF or image)."""
    uid = user["uid"]

    content_type = file.content_type or ""
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {content_type}. Allowed: PDF, PNG, JPG, WEBP",
        )

    temp_path, header_bytes, total_size = await _spill_upload_to_tempfile(file)
    try:
        if total_size == 0:
            raise HTTPException(status_code=400, detail="Empty file")

        if not validate_file_content(header_bytes, content_type):
            raise HTTPException(
                status_code=400,
                detail=f"File content does not match declared type: {content_type}",
            )

        result = await upload_source(uid, temp_path, file.filename or "unknown", content_type)

        # Convert image to PDF
        if content_type.startswith("image/"):
            source_id = result["sourceId"]
            original_path = result["originalStoragePath"]
            pdf_path = await convert_image_to_pdf(uid, source_id, temp_path, original_path)
            result["convertedType"] = "application/pdf"
            result["convertedStoragePath"] = pdf_path
            result["status"] = "ready"

        return result
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass


@router.get("")
async def list_sources_endpoint(
    date: str = Query(
        default=None,
        description="Date in YYYY-MM-DD format. Defaults to today (KST).",
    ),
    user: dict = Depends(get_current_user),
):
    """List sources for the authenticated user on a given date."""
    uid = user["uid"]

    if date is None:
        date = datetime.now(KST).strftime("%Y-%m-%d")

    # Validate date format
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    sources = await list_sources(uid, date)
    return {"date": date, "sources": sources}


@router.delete("/{source_id}")
async def delete_source_endpoint(
    source_id: str,
    user: dict = Depends(get_current_user),
):
    """Delete a source by ID."""
    uid = user["uid"]
    deleted = await delete_source(uid, source_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Source not found")
    return {"deleted": True, "sourceId": source_id}
