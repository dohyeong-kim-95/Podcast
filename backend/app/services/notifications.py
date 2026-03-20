"""Web Push notification helpers."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from pywebpush import WebPushException, webpush

from app.services.db import get_db, json_dumps, utc_now

logger = logging.getLogger(__name__)


def _vapid_private_key() -> str:
    value = os.getenv("VAPID_PRIVATE_KEY", "").strip()
    if not value:
        raise RuntimeError("VAPID_PRIVATE_KEY not configured")
    return value


def _vapid_subject() -> str:
    value = os.getenv("VAPID_SUBJECT", "").strip()
    if not value:
        raise RuntimeError("VAPID_SUBJECT not configured")
    return value


def upsert_user_profile(uid: str, email: str | None, display_name: str | None) -> None:
    now = utc_now()
    with get_db() as conn, conn.cursor() as cur:
        cur.execute(
            """
            insert into profiles (id, email, display_name, created_at, last_login_at)
            values (%s, %s, %s, %s, %s)
            on conflict (id) do update
            set email = excluded.email,
                display_name = excluded.display_name,
                last_login_at = excluded.last_login_at
            """,
            (uid, email, display_name, now, now),
        )


def save_push_subscription(
    uid: str,
    subscription: dict[str, Any],
    *,
    email: str | None = None,
    display_name: str | None = None,
) -> None:
    endpoint = subscription.get("endpoint")
    if not endpoint:
        raise ValueError("Push subscription endpoint missing")

    upsert_user_profile(uid, email, display_name)

    with get_db() as conn, conn.cursor() as cur:
        cur.execute(
            """
            insert into push_subscriptions (user_id, endpoint, subscription, updated_at)
            values (%s, %s, %s::jsonb, %s)
            on conflict (user_id) do update
            set endpoint = excluded.endpoint,
                subscription = excluded.subscription,
                updated_at = excluded.updated_at
            """,
            (uid, endpoint, json_dumps(subscription), utc_now()),
        )


def clear_push_subscription(uid: str) -> None:
    with get_db() as conn, conn.cursor() as cur:
        cur.execute("delete from push_subscriptions where user_id = %s", (uid,))


def get_push_subscription(uid: str) -> dict[str, Any] | None:
    with get_db() as conn, conn.cursor() as cur:
        cur.execute(
            "select subscription from push_subscriptions where user_id = %s",
            (uid,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return row["subscription"]


def _is_invalid_subscription_error(exc: Exception) -> bool:
    if isinstance(exc, WebPushException):
        response = getattr(exc, "response", None)
        if response is not None and getattr(response, "status_code", None) in {404, 410}:
            return True
    text = str(exc).upper()
    return "UNREGISTERED" in text or "410" in text or "404" in text


def send_push_to_user(uid: str, *, title: str, body: str, link: str = "/") -> bool:
    subscription = get_push_subscription(uid)
    if not subscription:
        return False

    payload = {
        "title": title,
        "body": body,
        "data": {"url": link},
    }

    try:
        webpush(
            subscription_info=subscription,
            data=json.dumps(payload),
            vapid_private_key=_vapid_private_key(),
            vapid_claims={"sub": _vapid_subject()},
            ttl=60,
        )
        return True
    except Exception as exc:  # pragma: no cover - provider-specific behavior
        if _is_invalid_subscription_error(exc):
            logger.warning("Clearing invalid push subscription for %s: %s", uid, exc)
            clear_push_subscription(uid)
            return False
        raise

