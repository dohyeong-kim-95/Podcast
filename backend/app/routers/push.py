"""Push token and download reminder APIs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.middleware.auth import get_current_user, verify_scheduler_token
from app.services.firebase import get_firestore_client
from app.services.notifications import save_push_token, send_push_to_user

router = APIRouter(prefix="/api", tags=["push"])

KST = timezone(timedelta(hours=9))


class PushTokenRequest(BaseModel):
    token: str


@router.post("/push-token")
async def register_push_token(
    body: PushTokenRequest,
    user: dict = Depends(get_current_user),
):
    """Store the authenticated user's FCM token."""
    save_push_token(
        user["uid"],
        body.token,
        email=user.get("email"),
        display_name=user.get("name"),
    )
    return {"registered": True}


@router.post("/remind-download")
async def remind_download(
    claims: dict = Depends(verify_scheduler_token),
):
    """Send reminders to users who have not downloaded today's podcast."""
    date_str = datetime.now(KST).strftime("%Y-%m-%d")
    db = get_firestore_client()

    reminded = []
    skipped = 0
    for doc in db.collection("podcasts").where("date", "==", date_str).stream():
        data = doc.to_dict()
        if data.get("status") != "completed" or data.get("downloaded"):
            skipped += 1
            continue

        uid = data.get("uid")
        if not uid:
            skipped += 1
            continue

        sent = send_push_to_user(
            uid,
            title="오늘 팟캐스트를 저장해 두세요",
            body="내일이면 삭제됩니다. 지금 다운로드해 두세요.",
            link="/",
        )
        if sent:
            reminded.append(uid)
        else:
            skipped += 1

    return {
        "status": "done",
        "date": date_str,
        "reminded": reminded,
        "sentCount": len(reminded),
        "skippedCount": skipped,
    }
