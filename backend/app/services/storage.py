import uuid
from datetime import datetime, timezone, timedelta

from firebase_admin import storage, firestore

from app.services.firebase import get_firestore_client

KST = timezone(timedelta(hours=9))

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/webp",
}

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB


def _today_date_str() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def _get_bucket():
    return storage.bucket()


async def upload_source(uid: str, file_bytes: bytes, filename: str, content_type: str) -> dict:
    """Upload a source file to Storage and create Firestore metadata."""
    source_id = uuid.uuid4().hex[:12]
    date_str = _today_date_str()
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    storage_path = f"sources/{uid}/{date_str}/{source_id}.{ext}"

    bucket = _get_bucket()
    blob = bucket.blob(storage_path)
    blob.upload_from_string(file_bytes, content_type=content_type)

    doc_data = {
        "uid": uid,
        "fileName": filename,
        "originalType": content_type,
        "convertedType": None,
        "storagePath": storage_path,
        "uploadedAt": firestore.SERVER_TIMESTAMP,
        "windowDate": date_str,
        "status": "uploaded",
    }

    db = get_firestore_client()
    db.collection("sources").document(source_id).set(doc_data)

    doc_data["sourceId"] = source_id
    doc_data["uploadedAt"] = datetime.now(KST).isoformat()
    return doc_data


async def convert_image_to_pdf(uid: str, source_id: str, file_bytes: bytes, original_storage_path: str) -> str:
    """Convert an image to PDF using img2pdf and store alongside original."""
    import img2pdf as _img2pdf

    pdf_bytes = _img2pdf.convert(file_bytes)

    pdf_path = original_storage_path.rsplit(".", 1)[0] + ".pdf"

    bucket = _get_bucket()
    blob = bucket.blob(pdf_path)
    blob.upload_from_string(pdf_bytes, content_type="application/pdf")

    db = get_firestore_client()
    db.collection("sources").document(source_id).update({
        "convertedType": "application/pdf",
        "storagePath": pdf_path,
        "status": "ready",
    })

    return pdf_path


async def list_sources(uid: str, date: str) -> list[dict]:
    """List sources for a user on a given date."""
    db = get_firestore_client()
    query = (
        db.collection("sources")
        .where("uid", "==", uid)
        .where("windowDate", "==", date)
        .where("status", "in", ["uploaded", "processing", "ready", "used"])
        .order_by("uploadedAt")
    )
    docs = query.stream()
    results = []
    for doc in docs:
        data = doc.to_dict()
        data["sourceId"] = doc.id
        uploaded_at = data.get("uploadedAt")
        if uploaded_at and hasattr(uploaded_at, "isoformat"):
            data["uploadedAt"] = uploaded_at.isoformat()
        results.append(data)
    return results


async def delete_source(uid: str, source_id: str) -> bool:
    """Delete a source from Storage and Firestore. Returns True if found."""
    db = get_firestore_client()
    doc_ref = db.collection("sources").document(source_id)
    doc = doc_ref.get()

    if not doc.exists:
        return False

    data = doc.to_dict()
    if data.get("uid") != uid:
        return False

    # Delete from Storage
    bucket = _get_bucket()
    storage_path = data.get("storagePath", "")
    if storage_path:
        blob = bucket.blob(storage_path)
        if blob.exists():
            blob.delete()

    # If there was an original file with different extension, try to delete it too
    original_type = data.get("originalType", "")
    if data.get("convertedType") and original_type.startswith("image/"):
        ext_map = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
        orig_ext = ext_map.get(original_type)
        if orig_ext:
            orig_path = storage_path.rsplit(".", 1)[0] + "." + orig_ext
            if orig_path != storage_path:
                orig_blob = bucket.blob(orig_path)
                if orig_blob.exists():
                    orig_blob.delete()

    doc_ref.delete()
    return True
