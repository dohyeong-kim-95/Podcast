"""T-032: Podcast generation pipeline.

POST /api/generate      — Called by Cloud Scheduler @ 06:40 KST
POST /api/generate/me   — Manual trigger by authenticated user
GET  /api/podcasts/today — Get today's podcast for authenticated user
POST /api/podcasts/{podcastId}/feedback — Submit feedback
"""

import asyncio
import logging
import tempfile
import os
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from firebase_admin import firestore, storage
from pydantic import BaseModel

from app.middleware.auth import get_current_user, verify_scheduler_token
from app.services.firebase import get_firestore_client
from app.services.instructions import build_instructions
from app.services.notebook import NotebookLMClient, load_nb_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["podcast"])

KST = timezone(timedelta(hours=9))

# Statuses that indicate generation is already in progress or done
_SKIP_STATUSES = {"completed", "generating", "retry_1", "retry_2", "no_sources"}


def _today_kst() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def _window_cutoff(date_str: str) -> tuple[datetime, datetime]:
    """Return (start, end) of the 06:40 source collection window.

    Window: previous day 06:40 KST → given day 06:40 KST.
    """
    date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=KST)
    end = date.replace(hour=6, minute=40, second=0, microsecond=0)
    start = end - timedelta(days=1)
    return start, end


def _podcast_id(uid: str, date_str: str) -> str:
    return f"{uid}-{date_str}"


async def _get_user_memory(uid: str) -> dict | None:
    """Load user memory from Firestore."""
    db = get_firestore_client()
    doc = db.collection("users").document(uid).get()
    if not doc.exists:
        return None
    return doc.to_dict().get("memory")


async def _get_sources_for_window(uid: str, date_str: str) -> list[dict]:
    """Query sources within the 06:40 window for a user."""
    db = get_firestore_client()
    start, end = _window_cutoff(date_str)

    # Query sources by windowDate (yesterday and today cover the window)
    yesterday = (datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")

    sources = []
    for window_date in [yesterday, date_str]:
        query = (
            db.collection("sources")
            .where("uid", "==", uid)
            .where("windowDate", "==", window_date)
            .where("status", "in", ["uploaded", "processing", "ready"])
        )
        for doc in query.stream():
            data = doc.to_dict()
            uploaded_at = data.get("uploadedAt")
            # Filter by exact window time if uploadedAt is available
            if uploaded_at and hasattr(uploaded_at, "timestamp"):
                ts = uploaded_at.replace(tzinfo=timezone.utc) if uploaded_at.tzinfo is None else uploaded_at
                if ts < start or ts >= end:
                    continue
            data["sourceId"] = doc.id
            sources.append(data)

    return sources


async def _download_source_pdf(source: dict) -> str | None:
    """Download source PDF from Storage to a temp file. Returns temp file path."""
    # Use converted PDF if available, otherwise original (must be PDF)
    storage_path = source.get("convertedStoragePath") or source.get("originalStoragePath")
    if not storage_path:
        return None

    # Ensure it's a PDF
    original_type = source.get("originalType", "")
    converted_type = source.get("convertedType")
    if converted_type != "application/pdf" and original_type != "application/pdf":
        return None

    bucket = storage.bucket()
    blob = bucket.blob(storage_path)

    if not blob.exists():
        logger.warning("Source blob not found: %s", storage_path)
        return None

    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    blob.download_to_filename(tmp.name)
    tmp.close()
    return tmp.name


async def _update_podcast_status(podcast_id: str, status: str, **extra_fields):
    """Update podcast document status and optional extra fields."""
    db = get_firestore_client()
    update = {"status": status, **extra_fields}
    db.collection("podcasts").document(podcast_id).set(update, merge=True)


async def _mark_sources_used(source_ids: list[str]):
    """Mark sources as 'used' after successful generation."""
    db = get_firestore_client()
    for sid in source_ids:
        db.collection("sources").document(sid).update({"status": "used"})


async def _delete_previous_audio(uid: str, today_str: str):
    """Delete previous day's podcast audio from Storage."""
    yesterday = (datetime.strptime(today_str, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    old_path = f"podcasts/{uid}/{yesterday}.mp3"
    bucket = storage.bucket()
    blob = bucket.blob(old_path)
    if blob.exists():
        blob.delete()
        logger.info("Deleted old podcast audio: %s", old_path)


async def _generate_for_user(uid: str, date_str: str) -> dict:
    """Run the full podcast generation pipeline for a single user.

    Returns:
        Result dict with status and details.
    """
    podcast_id = _podcast_id(uid, date_str)

    # Check existing status
    db = get_firestore_client()
    existing = db.collection("podcasts").document(podcast_id).get()
    if existing.exists:
        current_status = existing.to_dict().get("status", "")
        if current_status in _SKIP_STATUSES:
            return {"uid": uid, "skipped": True, "reason": f"status={current_status}"}

    # Set to generating
    await _update_podcast_status(
        podcast_id,
        "generating",
        uid=uid,
        date=date_str,
    )

    # Get sources
    sources = await _get_sources_for_window(uid, date_str)
    if not sources:
        await _update_podcast_status(
            podcast_id,
            "no_sources",
            uid=uid,
            date=date_str,
            sourceCount=0,
            sourceIds=[],
            generatedAt=firestore.SERVER_TIMESTAMP,
        )
        logger.info("No sources for user %s on %s, skipping", uid, date_str)
        return {"uid": uid, "skipped": True, "reason": "no_sources"}

    source_ids = [s["sourceId"] for s in sources]

    # Load user memory and build instructions
    memory = await _get_user_memory(uid)
    instructions = build_instructions(memory)

    # Load NB session
    try:
        session = await load_nb_session(uid)
    except ValueError as e:
        await _update_podcast_status(
            podcast_id,
            "failed",
            error=f"nb_session: {e}",
            generatedAt=firestore.SERVER_TIMESTAMP,
        )
        logger.error("NB session error for user %s: %s", uid, e)
        return {"uid": uid, "error": str(e)}

    # Download source PDFs
    pdf_paths: list[str] = []
    try:
        for source in sources:
            path = await _download_source_pdf(source)
            if path:
                pdf_paths.append(path)

        if not pdf_paths:
            await _update_podcast_status(
                podcast_id,
                "failed",
                error="no_valid_pdf_sources",
                generatedAt=firestore.SERVER_TIMESTAMP,
            )
            return {"uid": uid, "error": "no_valid_pdf_sources"}

        # NotebookLM pipeline
        nb_client = NotebookLMClient(session["storageState"])
        notebook_id = None
        try:
            notebook_id = await nb_client.create_notebook(title=f"Podcast {date_str}")

            for pdf_path in pdf_paths:
                await nb_client.add_source(notebook_id, pdf_path)

            mp3_bytes = await nb_client.generate_audio(notebook_id, instructions)

            # Upload mp3 to Storage
            audio_path = f"podcasts/{uid}/{date_str}.mp3"
            bucket = storage.bucket()
            blob = bucket.blob(audio_path)
            blob.upload_from_string(mp3_bytes, content_type="audio/mpeg")

            # Estimate duration (rough: mp3 ~16kB/s at 128kbps)
            duration_seconds = max(1, len(mp3_bytes) // 16000)

            # Update podcast doc
            await _update_podcast_status(
                podcast_id,
                "completed",
                uid=uid,
                date=date_str,
                sourceIds=source_ids,
                sourceCount=len(source_ids),
                audioPath=audio_path,
                durationSeconds=duration_seconds,
                generatedAt=firestore.SERVER_TIMESTAMP,
                instructionsUsed=instructions,
                error=None,
                feedback=None,
                downloaded=False,
            )

            # Mark sources as used
            await _mark_sources_used(source_ids)

            # Delete previous day's audio
            await _delete_previous_audio(uid, date_str)

            logger.info("Podcast generated for user %s: %s", uid, audio_path)
            return {"uid": uid, "status": "completed", "audioPath": audio_path}

        except Exception as e:
            # Handle retry progression
            current_doc = db.collection("podcasts").document(podcast_id).get()
            current_status = current_doc.to_dict().get("status", "generating") if current_doc.exists else "generating"

            if current_status in ("generating", "pending"):
                next_status = "retry_1"
            elif current_status == "retry_1":
                next_status = "retry_2"
            else:
                next_status = "failed"

            await _update_podcast_status(
                podcast_id,
                next_status,
                error=str(e),
            )
            logger.error("Generation failed for user %s: %s → %s", uid, e, next_status)
            return {"uid": uid, "error": str(e), "status": next_status}

        finally:
            if notebook_id:
                await nb_client.delete_notebook(notebook_id)
            await nb_client.close()

    finally:
        # Clean up temp PDF files
        for path in pdf_paths:
            try:
                os.unlink(path)
            except OSError:
                pass


# ─── Endpoints ────────────────────────────────────────────────


@router.post("/generate")
async def generate_all(
    background_tasks: BackgroundTasks,
    claims: dict = Depends(verify_scheduler_token),
):
    """Cloud Scheduler endpoint: generate podcasts for all whitelisted users."""
    date_str = _today_kst()

    allowed_emails_raw = os.getenv("ALLOWED_EMAILS", "")
    allowed_emails = [e.strip() for e in allowed_emails_raw.split(",") if e.strip()]

    if not allowed_emails:
        return {"status": "no_users", "date": date_str}

    # Look up UIDs from whitelisted emails
    db = get_firestore_client()
    users: list[dict] = []
    for email in allowed_emails:
        query = db.collection("users").where("email", "==", email).limit(1)
        for doc in query.stream():
            users.append({"uid": doc.id, "email": email})

    if not users:
        return {"status": "no_users_found", "date": date_str}

    # Run generation in parallel for all users
    tasks = [_generate_for_user(u["uid"], date_str) for u in users]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    summary = []
    for user, result in zip(users, results):
        if isinstance(result, Exception):
            summary.append({"uid": user["uid"], "error": str(result)})
        else:
            summary.append(result)

    return {"status": "done", "date": date_str, "results": summary}


@router.post("/generate/me")
async def generate_me(
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    """Manual trigger: generate podcast for the authenticated user."""
    uid = user["uid"]
    date_str = _today_kst()
    podcast_id = _podcast_id(uid, date_str)

    # Atomically check status and claim "generating" via Firestore transaction
    db = get_firestore_client()
    doc_ref = db.collection("podcasts").document(podcast_id)
    transaction = db.transaction()

    @firestore.transactional
    def _claim_generating(txn, ref):
        snapshot = ref.get(transaction=txn)
        if snapshot.exists:
            status = snapshot.to_dict().get("status", "")
            if status in ("generating", "completed", "no_sources"):
                return status  # Already claimed
        txn.set(ref, {
            "status": "generating",
            "uid": uid,
            "date": date_str,
        }, merge=True)
        return None  # Successfully claimed

    existing_status = _claim_generating(transaction, doc_ref)
    if existing_status:
        raise HTTPException(
            status_code=409,
            detail=f"Podcast already {existing_status} for today",
        )

    # Run generation in background
    background_tasks.add_task(_generate_for_user, uid, date_str)

    return {"status": "generating", "date": date_str, "podcastId": podcast_id}


@router.get("/podcasts/today")
async def get_today_podcast(
    user: dict = Depends(get_current_user),
):
    """Get today's podcast for the authenticated user."""
    uid = user["uid"]
    date_str = _today_kst()
    podcast_id = _podcast_id(uid, date_str)

    db = get_firestore_client()
    doc = db.collection("podcasts").document(podcast_id).get()

    if not doc.exists:
        return {"podcast": None, "date": date_str}

    data = doc.to_dict()
    data["podcastId"] = doc.id

    # Generate signed URL if completed
    if data.get("status") == "completed" and data.get("audioPath"):
        bucket = storage.bucket()
        blob = bucket.blob(data["audioPath"])
        if blob.exists():
            url = blob.generate_signed_url(expiration=timedelta(hours=6))
            data["audioUrl"] = url

    # Convert timestamps
    for ts_field in ("generatedAt",):
        val = data.get(ts_field)
        if val and hasattr(val, "isoformat"):
            data[ts_field] = val.isoformat()

    return {"podcast": data, "date": date_str}


class FeedbackRequest(BaseModel):
    rating: str  # "good" | "normal" | "bad"


@router.post("/podcasts/{podcast_id}/feedback")
async def submit_feedback(
    podcast_id: str,
    body: FeedbackRequest,
    user: dict = Depends(get_current_user),
):
    """Submit feedback for a podcast."""
    uid = user["uid"]

    if body.rating not in ("good", "normal", "bad"):
        raise HTTPException(status_code=400, detail="Rating must be good, normal, or bad")

    db = get_firestore_client()
    doc_ref = db.collection("podcasts").document(podcast_id)
    doc = doc_ref.get()

    if not doc.exists:
        raise HTTPException(status_code=404, detail="Podcast not found")

    data = doc.to_dict()
    if data.get("uid") != uid:
        raise HTTPException(status_code=404, detail="Podcast not found")

    doc_ref.update({"feedback": body.rating})

    # Also append to user's feedback history in memory
    date_str = data.get("date", _today_kst())
    user_ref = db.collection("users").document(uid)
    user_doc = user_ref.get()
    if user_doc.exists:
        user_data = user_doc.to_dict()
        memory = user_data.get("memory", {})
        history = memory.get("feedbackHistory", [])
        history.append({"date": date_str, "rating": body.rating})
        # Keep only last 20 entries
        memory["feedbackHistory"] = history[-20:]
        user_ref.update({"memory": memory})

    return {"podcastId": podcast_id, "feedback": body.rating}
