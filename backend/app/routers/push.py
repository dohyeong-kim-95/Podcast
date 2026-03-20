"""Push subscription and reminder APIs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.middleware.auth import get_current_user, verify_scheduler_token
from app.services.db import get_db, serialize_date
from app.services.notifications import save_push_subscription, send_push_to_user

router = APIRouter(prefix="/api", tags=["push"])

KST = timezone(timedelta(hours=9))


class PushSubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscriptionPayload(BaseModel):
    endpoint: str
    expirationTime: int | None = None
    keys: PushSubscriptionKeys


class PushSubscriptionRequest(BaseModel):
    subscription: PushSubscriptionPayload


@router.post("/push-token")
async def register_push_subscription(
    body: PushSubscriptionRequest,
    user: dict = Depends(get_current_user),
):
    """Store the authenticated user's Web Push subscription."""
    save_push_subscription(
        user["uid"],
        body.subscription.model_dump(),
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

    reminded: list[str] = []
    skipped = 0

    with get_db() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select user_id
            from podcasts
            where date = %s::date
              and status = 'completed'
              and downloaded = false
            """,
            (date_str,),
        )
        rows = cur.fetchall()

    for row in rows:
        uid = row.get("user_id")
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
