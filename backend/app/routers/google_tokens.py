"""Endpoint to receive and store Google OAuth tokens from the frontend callback."""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.middleware.auth import get_current_user
from app.services.google_tokens import save_google_tokens

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/google-tokens", tags=["google_tokens"])


class GoogleTokensRequest(BaseModel):
    accessToken: str
    refreshToken: str | None = None


class GoogleTokensResponse(BaseModel):
    saved: bool
    hasRefreshToken: bool = False


@router.post("", response_model=GoogleTokensResponse)
async def store_google_tokens(
    body: GoogleTokensRequest,
    user: dict = Depends(get_current_user),
):
    uid = user["uid"]
    logger.info(
        "[google_tokens_router] POST /api/google-tokens: uid=%s, accessToken_len=%d, has_refreshToken=%s",
        uid, len(body.accessToken), body.refreshToken is not None,
    )

    try:
        result = await save_google_tokens(
            uid,
            access_token=body.accessToken,
            refresh_token=body.refreshToken,
        )
    except Exception as exc:
        logger.error("[google_tokens_router] save_google_tokens FAILED for %s: %s", uid, exc, exc_info=True)
        raise

    logger.info(
        "[google_tokens_router] Stored Google tokens for user %s (hasRefresh=%s)",
        uid, result.get("hasRefreshToken"),
    )
    return GoogleTokensResponse(
        saved=result["saved"],
        hasRefreshToken=result.get("hasRefreshToken", False),
    )
