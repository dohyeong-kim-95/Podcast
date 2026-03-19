import os
from typing import Optional

from fastapi import Depends, HTTPException, Request
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from app.services.firebase import verify_id_token


def _get_allowed_emails() -> set[str]:
    raw = os.getenv("ALLOWED_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


async def get_current_user(request: Request) -> dict:
    """Firebase ID token 검증 + 이메일 화이트리스트 체크.

    사용자 API용 의존성.
    Returns decoded token claims dict with uid, email, etc.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth_header.split("Bearer ", 1)[1]

    try:
        decoded = verify_id_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    email = decoded.get("email", "").lower()
    allowed = _get_allowed_emails()
    if allowed and email not in allowed:
        raise HTTPException(status_code=403, detail="Access denied: email not in whitelist")

    return decoded


async def verify_scheduler_token(request: Request) -> dict:
    """Cloud Scheduler OIDC token 검증.

    내부 API용 의존성 (/api/generate, /api/remind-download).
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth_header.split("Bearer ", 1)[1]
    audience = os.getenv("CLOUD_RUN_URL", "")

    if not audience:
        raise HTTPException(status_code=500, detail="CLOUD_RUN_URL not configured")

    try:
        claims = google_id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            audience=audience,
        )
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid OIDC token")

    # T-032-1: Validate service account email
    expected_sa = os.getenv("SCHEDULER_SERVICE_ACCOUNT", "")
    if expected_sa:
        token_email = claims.get("email", "")
        if token_email != expected_sa:
            raise HTTPException(
                status_code=403,
                detail="Unauthorized service account",
            )

    return claims
