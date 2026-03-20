"""Podcast generation pipeline."""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from app.middleware.auth import get_current_user, verify_scheduler_token
from app.services.db import get_db, json_dumps, serialize_date, serialize_timestamp, utc_now
from app.services.instructions import build_instructions
from app.services.notifications import send_push_to_user
from app.services.notebook import AUDIO_TIMEOUT_SECONDS, NotebookLMClient, load_nb_session
from app.services.storage import (
    create_podcast_audio_signed_url,
    delete_podcast_audio,
    download_bytes,
    upload_podcast_audio,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["podcast"])

KST = timezone(timedelta(hours=9))
_SKIP_STATUSES = {"completed", "generating", "retry_1", "retry_2", "no_sources"}


def _sources_bucket() -> str:
    return os.getenv("SUPABASE_STORAGE_BUCKET_SOURCES", "sources").strip() or "sources"


def _today_kst() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def _generate_concurrency_limit() -> int:
    raw = os.getenv("GENERATE_MAX_CONCURRENCY", "4")
    try:
        return max(1, int(raw))
    except ValueError:
        logger.warning("Invalid GENERATE_MAX_CONCURRENCY=%r, falling back to 4", raw)
        return 4


def _window_cutoff(date_str: str) -> tuple[datetime, datetime]:
    date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=KST)
    end = date.replace(hour=6, minute=40, second=0, microsecond=0)
    start = end - timedelta(days=1)
    return start, end


def _podcast_id(uid: str, date_str: str) -> str:
    return f"{uid}-{date_str}"


def _default_podcast_record(podcast_id: str) -> dict:
    return {
        "id": podcast_id,
        "user_id": None,
        "date": None,
        "status": None,
        "source_ids": [],
        "source_count": 0,
        "audio_path": None,
        "duration_seconds": None,
        "generated_at": None,
        "instructions_used": None,
        "error": None,
        "feedback": None,
        "downloaded": False,
    }


def _fetch_podcast_record(podcast_id: str) -> dict | None:
    with get_db() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select
                id,
                user_id,
                date,
                status,
                source_ids,
                source_count,
                audio_path,
                duration_seconds,
                generated_at,
                instructions_used,
                error,
                feedback,
                downloaded
            from podcasts
            where id = %s
            """,
            (podcast_id,),
        )
        return cur.fetchone()


def _save_podcast_record(record: dict) -> None:
    with get_db() as conn, conn.cursor() as cur:
        cur.execute(
            """
            insert into podcasts (
                id,
                user_id,
                date,
                status,
                source_ids,
                source_count,
                audio_path,
                duration_seconds,
                generated_at,
                instructions_used,
                error,
                feedback,
                downloaded
            )
            values (%s, %s, %s::date, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (id) do update
            set user_id = excluded.user_id,
                date = excluded.date,
                status = excluded.status,
                source_ids = excluded.source_ids,
                source_count = excluded.source_count,
                audio_path = excluded.audio_path,
                duration_seconds = excluded.duration_seconds,
                generated_at = excluded.generated_at,
                instructions_used = excluded.instructions_used,
                error = excluded.error,
                feedback = excluded.feedback,
                downloaded = excluded.downloaded
            """,
            (
                record["id"],
                record["user_id"],
                record["date"],
                record["status"],
                json_dumps(record.get("source_ids") or []),
                record.get("source_count") or 0,
                record.get("audio_path"),
                record.get("duration_seconds"),
                record.get("generated_at"),
                record.get("instructions_used"),
                record.get("error"),
                record.get("feedback"),
                bool(record.get("downloaded", False)),
            ),
        )


def _apply_podcast_update(record: dict, **extra_fields) -> dict:
    mapping = {
        "uid": "user_id",
        "date": "date",
        "sourceIds": "source_ids",
        "sourceCount": "source_count",
        "audioPath": "audio_path",
        "durationSeconds": "duration_seconds",
        "generatedAt": "generated_at",
        "instructionsUsed": "instructions_used",
        "feedback": "feedback",
        "downloaded": "downloaded",
        "error": "error",
        "status": "status",
    }
    for key, value in extra_fields.items():
        target = mapping.get(key, key)
        record[target] = value
    return record


async def _update_podcast_status(podcast_id: str, status: str, **extra_fields) -> None:
    record = _fetch_podcast_record(podcast_id) or _default_podcast_record(podcast_id)
    record["status"] = status
    _apply_podcast_update(record, **extra_fields)
    _save_podcast_record(record)


async def _get_user_memory(uid: str) -> dict | None:
    with get_db() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select interests, tone, depth, custom, feedback_history
            from user_memory
            where user_id = %s
            """,
            (uid,),
        )
        row = cur.fetchone()

    if not row:
        return None

    return {
        "interests": row["interests"],
        "tone": row["tone"],
        "preferredTone": row["tone"],
        "depth": row["depth"],
        "preferredDepth": row["depth"],
        "custom": row["custom"],
        "customInstructions": row["custom"],
        "feedbackHistory": row["feedback_history"] or [],
    }


async def _get_sources_for_window(uid: str, date_str: str) -> list[dict]:
    start, end = _window_cutoff(date_str)
    yesterday = (datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")

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
              and window_date = any(%s::date[])
              and status = any(%s)
              and uploaded_at >= %s
              and uploaded_at < %s
            order by uploaded_at asc
            """,
            (uid, [yesterday, date_str], ["uploaded", "processing", "ready"], start, end),
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
            "uploadedAt": row["uploaded_at"],
            "windowDate": serialize_date(row["window_date"]),
            "status": row["status"],
        }
        for row in rows
    ]


async def _download_source_pdf(source: dict) -> str | None:
    storage_path = source.get("convertedStoragePath") or source.get("originalStoragePath")
    if not storage_path:
        return None

    original_type = source.get("originalType", "")
    converted_type = source.get("convertedType")
    if converted_type != "application/pdf" and original_type != "application/pdf":
        return None

    try:
        payload = download_bytes(_sources_bucket(), storage_path)
    except Exception:
        logger.warning("Source blob not found: %s", storage_path)
        return None

    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.write(payload)
    tmp.close()
    return tmp.name


async def _mark_sources_used(source_ids: list[str]) -> None:
    if not source_ids:
        return
    with get_db() as conn, conn.cursor() as cur:
        cur.execute(
            "update sources set status = 'used' where id = any(%s)",
            (source_ids,),
        )


async def _delete_previous_audio(uid: str, today_str: str) -> None:
    yesterday = (datetime.strptime(today_str, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    delete_podcast_audio(f"podcasts/{uid}/{yesterday}.mp3")


def _notify_user(uid: str, *, title: str, body: str, link: str = "/") -> None:
    try:
        send_push_to_user(uid, title=title, body=body, link=link)
    except Exception as exc:
        logger.warning("Push notification failed for user %s: %s", uid, exc)


async def _generate_for_user(uid: str, date_str: str) -> dict:
    podcast_id = _podcast_id(uid, date_str)

    existing = _fetch_podcast_record(podcast_id)
    if existing:
        current_status = existing.get("status", "")
        if current_status in _SKIP_STATUSES:
            return {"uid": uid, "skipped": True, "reason": f"status={current_status}"}

    await _update_podcast_status(
        podcast_id,
        "generating",
        uid=uid,
        date=date_str,
        downloaded=False,
    )

    sources = await _get_sources_for_window(uid, date_str)
    if not sources:
        await _update_podcast_status(
            podcast_id,
            "no_sources",
            uid=uid,
            date=date_str,
            sourceCount=0,
            sourceIds=[],
            generatedAt=utc_now(),
        )
        logger.info("No sources for user %s on %s, skipping", uid, date_str)
        _notify_user(
            uid,
            title="오늘은 소스가 없어요",
            body="내일 아침 팟캐스트를 위해 오늘 소스를 업로드해 보세요.",
        )
        return {"uid": uid, "skipped": True, "reason": "no_sources"}

    source_ids = [s["sourceId"] for s in sources]
    memory = await _get_user_memory(uid)
    instructions = build_instructions(memory)

    try:
        session = await load_nb_session(uid)
    except ValueError as exc:
        await _update_podcast_status(
            podcast_id,
            "failed",
            error=f"nb_session: {exc}",
            generatedAt=utc_now(),
        )
        logger.error("NB session error for user %s: %s", uid, exc)
        _notify_user(
            uid,
            title="NotebookLM 세션 재인증이 필요합니다",
            body="세션이 만료되었거나 유효하지 않습니다. 앱에서 다시 로그인해 주세요.",
            link="/settings",
        )
        return {"uid": uid, "error": str(exc)}

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
                generatedAt=utc_now(),
            )
            return {"uid": uid, "error": "no_valid_pdf_sources"}

        nb_client = NotebookLMClient(session["storageState"])
        notebook_id = None
        try:
            notebook_id = await nb_client.create_notebook(title=f"Podcast {date_str}")

            for pdf_path in pdf_paths:
                await nb_client.add_source(notebook_id, pdf_path)

            mp3_bytes = await asyncio.wait_for(
                nb_client.generate_audio(notebook_id, instructions),
                timeout=AUDIO_TIMEOUT_SECONDS,
            )

            audio_path = f"podcasts/{uid}/{date_str}.mp3"
            upload_podcast_audio(audio_path, mp3_bytes)
            duration_seconds = max(1, len(mp3_bytes) // 16000)

            await _update_podcast_status(
                podcast_id,
                "completed",
                uid=uid,
                date=date_str,
                sourceIds=source_ids,
                sourceCount=len(source_ids),
                audioPath=audio_path,
                durationSeconds=duration_seconds,
                generatedAt=utc_now(),
                instructionsUsed=instructions,
                error=None,
                feedback=None,
                downloaded=False,
            )

            await _mark_sources_used(source_ids)
            await _delete_previous_audio(uid, date_str)

            logger.info("Podcast generated for user %s: %s", uid, audio_path)
            _notify_user(
                uid,
                title="오늘의 팟캐스트가 준비됐어요",
                body="앱을 열어 바로 재생하거나 다운로드할 수 있습니다.",
            )
            return {"uid": uid, "status": "completed", "audioPath": audio_path}
        except asyncio.TimeoutError:
            await _update_podcast_status(
                podcast_id,
                "failed",
                error="audio_timeout",
            )
            logger.error("Audio generation timed out for user %s after %ss", uid, AUDIO_TIMEOUT_SECONDS)
            return {"uid": uid, "error": "audio_timeout", "status": "failed"}
        except Exception as exc:
            current = _fetch_podcast_record(podcast_id) or {}
            current_status = current.get("status", "generating")

            if current_status in ("generating", "pending"):
                next_status = "retry_1"
            elif current_status == "retry_1":
                next_status = "retry_2"
            else:
                next_status = "failed"

            await _update_podcast_status(
                podcast_id,
                next_status,
                error=str(exc),
            )
            logger.error("Generation failed for user %s: %s -> %s", uid, exc, next_status)
            return {"uid": uid, "error": str(exc), "status": next_status}
        finally:
            if notebook_id:
                await nb_client.delete_notebook(notebook_id)
            await nb_client.close()
    finally:
        for path in pdf_paths:
            try:
                os.unlink(path)
            except OSError:
                pass


@router.post("/generate")
async def generate_all(
    background_tasks: BackgroundTasks,
    claims: dict = Depends(verify_scheduler_token),
):
    """Cloud Scheduler endpoint: generate podcasts for all whitelisted users."""
    date_str = _today_kst()

    allowed_emails_raw = os.getenv("ALLOWED_EMAILS", "")
    allowed_emails = [e.strip().lower() for e in allowed_emails_raw.split(",") if e.strip()]

    if not allowed_emails:
        return {"status": "no_users", "date": date_str}

    with get_db() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select id as uid, email
            from profiles
            where lower(email) = any(%s)
            """,
            (allowed_emails,),
        )
        users = cur.fetchall()

    if not users:
        return {"status": "no_users_found", "date": date_str}

    semaphore = asyncio.Semaphore(_generate_concurrency_limit())

    async def _run_generation(uid: str):
        async with semaphore:
            return await _generate_for_user(uid, date_str)

    tasks = [_run_generation(user["uid"]) for user in users]
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

    with get_db() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select status
            from podcasts
            where id = %s
            for update
            """,
            (podcast_id,),
        )
        row = cur.fetchone()
        if row and row.get("status") in ("generating", "completed", "no_sources"):
            raise HTTPException(
                status_code=409,
                detail=f"Podcast already {row['status']} for today",
            )

        if row:
            cur.execute(
                """
                update podcasts
                set status = %s,
                    user_id = %s,
                    date = %s::date,
                    error = null
                where id = %s
                """,
                ("generating", uid, date_str, podcast_id),
            )
        else:
            cur.execute(
                """
                insert into podcasts (id, user_id, date, status, source_ids, source_count, downloaded)
                values (%s, %s, %s::date, %s, %s::jsonb, %s, %s)
                """,
                (podcast_id, uid, date_str, "generating", json_dumps([]), 0, False),
            )

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

    row = _fetch_podcast_record(podcast_id)
    if not row:
        return {"podcast": None, "date": date_str}

    data = {
        "podcastId": row["id"],
        "uid": row["user_id"],
        "date": serialize_date(row["date"]),
        "status": row["status"],
        "sourceIds": row["source_ids"] or [],
        "sourceCount": row["source_count"],
        "audioPath": row["audio_path"],
        "durationSeconds": row["duration_seconds"],
        "generatedAt": serialize_timestamp(row["generated_at"]),
        "instructionsUsed": row["instructions_used"],
        "error": row["error"],
        "feedback": row["feedback"],
        "downloaded": row["downloaded"],
    }

    if data.get("status") == "completed" and data.get("audioPath"):
        try:
            data["audioUrl"] = create_podcast_audio_signed_url(data["audioPath"])
        except Exception as exc:
            logger.warning("Failed to sign podcast audio URL for %s: %s", podcast_id, exc)

    return {"podcast": data, "date": date_str}


@router.post("/podcasts/{podcast_id}/downloaded")
async def mark_downloaded(
    podcast_id: str,
    user: dict = Depends(get_current_user),
):
    """Mark a podcast as downloaded."""
    uid = user["uid"]

    with get_db() as conn, conn.cursor() as cur:
        cur.execute(
            """
            update podcasts
            set downloaded = true
            where id = %s and user_id = %s
            returning id
            """,
            (podcast_id, uid),
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Podcast not found")

    return {}


class FeedbackRequest(BaseModel):
    rating: str


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

    with get_db() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select id, date
            from podcasts
            where id = %s and user_id = %s
            """,
            (podcast_id, uid),
        )
        podcast_row = cur.fetchone()
        if not podcast_row:
            raise HTTPException(status_code=404, detail="Podcast not found")

        cur.execute(
            "update podcasts set feedback = %s where id = %s and user_id = %s",
            (body.rating, podcast_id, uid),
        )

        cur.execute(
            """
            select feedback_history
            from user_memory
            where user_id = %s
            for update
            """,
            (uid,),
        )
        memory_row = cur.fetchone()
        history = list((memory_row or {}).get("feedback_history") or [])
        history.append(
            {
                "date": serialize_date(podcast_row["date"]) or _today_kst(),
                "rating": body.rating,
            }
        )
        trimmed = history[-20:]

        cur.execute(
            """
            insert into user_memory (
                user_id,
                interests,
                tone,
                depth,
                custom,
                feedback_history,
                updated_at
            )
            values (%s, %s, %s, %s, %s, %s::jsonb, %s)
            on conflict (user_id) do update
            set feedback_history = excluded.feedback_history,
                updated_at = excluded.updated_at
            """,
            (
                uid,
                "",
                "",
                "",
                "",
                json_dumps(trimmed),
                utc_now(),
            ),
        )

    return {"podcastId": podcast_id, "feedback": body.rating}
