from datetime import datetime, timezone, timedelta

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

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File size exceeds 20MB limit")

    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    if not validate_file_content(file_bytes, content_type):
        raise HTTPException(
            status_code=400,
            detail=f"File content does not match declared type: {content_type}",
        )

    result = await upload_source(uid, file_bytes, file.filename or "unknown", content_type)

    # Convert image to PDF
    if content_type.startswith("image/"):
        source_id = result["sourceId"]
        original_path = result["originalStoragePath"]
        pdf_path = await convert_image_to_pdf(uid, source_id, file_bytes, original_path)
        result["convertedType"] = "application/pdf"
        result["convertedStoragePath"] = pdf_path
        result["status"] = "ready"

    return result


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
