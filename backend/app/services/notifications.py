"""Push notification helpers for reminder and generation events."""

from __future__ import annotations

import logging

from firebase_admin import firestore, messaging

from app.services.firebase import get_firestore_client

logger = logging.getLogger(__name__)


def upsert_user_profile(uid: str, email: str | None, display_name: str | None) -> None:
    """Ensure the Firestore user profile exists for later scheduler/push flows."""
    db = get_firestore_client()
    db.collection("users").document(uid).set(
        {
            "email": email,
            "displayName": display_name,
            "createdAt": firestore.SERVER_TIMESTAMP,
            "lastLoginAt": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )


def save_push_token(uid: str, token: str, *, email: str | None = None, display_name: str | None = None) -> None:
    """Store or refresh a user's FCM token."""
    db = get_firestore_client()
    db.collection("users").document(uid).set(
        {
            "email": email,
            "displayName": display_name,
            "createdAt": firestore.SERVER_TIMESTAMP,
            "lastLoginAt": firestore.SERVER_TIMESTAMP,
            "fcmToken": token,
            "fcmTokenUpdatedAt": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )


def clear_push_token(uid: str) -> None:
    """Remove an invalid FCM token."""
    db = get_firestore_client()
    db.collection("users").document(uid).set(
        {
            "fcmToken": firestore.DELETE_FIELD,
            "fcmTokenUpdatedAt": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )


def get_push_token(uid: str) -> str | None:
    """Look up a user's current FCM token."""
    db = get_firestore_client()
    doc = db.collection("users").document(uid).get()
    if not doc.exists:
        return None
    return doc.to_dict().get("fcmToken")


def _is_invalid_token_error(exc: Exception) -> bool:
    text = str(exc).upper()
    return "UNREGISTERED" in text or "REGISTRATION TOKEN" in text or "INVALID_ARGUMENT" in text


def send_push_to_user(uid: str, *, title: str, body: str, link: str = "/") -> bool:
    """Send a web push notification to a user if a valid token exists."""
    token = get_push_token(uid)
    if not token:
        return False

    message = messaging.Message(
        token=token,
        data={"url": link},
        notification=messaging.Notification(title=title, body=body),
        webpush=messaging.WebpushConfig(
            headers={"Urgency": "high"},
            data={"url": link},
            notification=messaging.WebpushNotification(
                title=title,
                body=body,
                data={"url": link},
            ),
            fcm_options=messaging.WebpushFCMOptions(link=link),
        ),
    )

    try:
        messaging.send(message)
        return True
    except Exception as exc:  # pragma: no cover - provider-specific typing
        if _is_invalid_token_error(exc):
            logger.warning("Clearing invalid FCM token for %s: %s", uid, exc)
            clear_push_token(uid)
            return False
        raise
