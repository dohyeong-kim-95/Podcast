"""Google OAuth token storage and refresh for server-side cookie exchange."""

import logging
import os
from typing import Any

import httpx
from cryptography.fernet import InvalidToken

from app.services.db import get_db, utc_now
from app.services.notebook import _get_fernet

logger = logging.getLogger(__name__)


def _google_client_id() -> str:
    value = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    if not value:
        logger.error("[google_tokens] GOOGLE_CLIENT_ID env var is empty or missing")
        raise RuntimeError("GOOGLE_CLIENT_ID not configured")
    logger.debug("[google_tokens] GOOGLE_CLIENT_ID loaded: %s...%s", value[:8], value[-4:])
    return value


def _google_client_secret() -> str:
    value = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    if not value:
        logger.error("[google_tokens] GOOGLE_CLIENT_SECRET env var is empty or missing")
        raise RuntimeError("GOOGLE_CLIENT_SECRET not configured")
    logger.debug("[google_tokens] GOOGLE_CLIENT_SECRET loaded (len=%d)", len(value))
    return value


def _encrypt(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def _decrypt(ciphertext: str) -> str:
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as e:
        logger.error("[google_tokens] Fernet decryption failed: %s", e)
        raise ValueError(f"Google token decryption failed: {e}") from e


async def save_google_tokens(
    uid: str,
    *,
    access_token: str | None = None,
    refresh_token: str | None = None,
    scope: str | None = None,
) -> dict[str, Any]:
    logger.info(
        "[google_tokens] save_google_tokens called: uid=%s, has_access=%s, has_refresh=%s, scope=%s",
        uid, bool(access_token), bool(refresh_token), scope,
    )

    if not refresh_token and not access_token:
        logger.warning("[google_tokens] Neither access_token nor refresh_token provided")
        raise ValueError("At least one of access_token or refresh_token is required")

    now = utc_now()

    with get_db() as conn, conn.cursor() as cur:
        cur.execute(
            "insert into profiles (id) values (%s) on conflict (id) do nothing",
            (uid,),
        )

        cur.execute(
            "select encrypted_refresh_token from google_tokens where user_id = %s",
            (uid,),
        )
        existing = cur.fetchone()
        logger.info("[google_tokens] Existing tokens for user %s: %s", uid, bool(existing))

        enc_refresh = _encrypt(refresh_token) if refresh_token else (
            existing["encrypted_refresh_token"] if existing else None
        )
        enc_access = _encrypt(access_token) if access_token else None

        if not enc_refresh:
            logger.warning("[google_tokens] No refresh_token and none stored for user %s", uid)
            raise ValueError("No refresh_token provided and none stored")

        cur.execute(
            """
            insert into google_tokens (
                user_id, encrypted_refresh_token, encrypted_access_token,
                token_scope, created_at, updated_at
            )
            values (%s, %s, %s, %s, %s, %s)
            on conflict (user_id) do update
            set encrypted_refresh_token = excluded.encrypted_refresh_token,
                encrypted_access_token = excluded.encrypted_access_token,
                token_scope = excluded.token_scope,
                updated_at = excluded.updated_at
            """,
            (uid, enc_refresh, enc_access, scope, now, now),
        )

    logger.info(
        "[google_tokens] Saved tokens for user %s (hasRefresh=%s)",
        uid, bool(refresh_token),
    )
    return {"saved": True, "hasRefreshToken": bool(refresh_token)}


async def load_google_tokens(uid: str) -> dict[str, Any]:
    logger.info("[google_tokens] load_google_tokens called: uid=%s", uid)

    with get_db() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select encrypted_refresh_token, encrypted_access_token,
                   token_scope, updated_at
            from google_tokens
            where user_id = %s
            """,
            (uid,),
        )
        row = cur.fetchone()

    if not row:
        logger.warning("[google_tokens] No tokens found for user %s", uid)
        raise ValueError("No Google tokens stored for this user")

    result: dict[str, Any] = {"updatedAt": row["updated_at"]}

    if row["encrypted_refresh_token"]:
        result["refreshToken"] = _decrypt(row["encrypted_refresh_token"])
        logger.info("[google_tokens] Decrypted refresh_token for user %s (len=%d)", uid, len(result["refreshToken"]))
    else:
        logger.warning("[google_tokens] No encrypted_refresh_token in DB for user %s", uid)

    if row["encrypted_access_token"]:
        result["accessToken"] = _decrypt(row["encrypted_access_token"])
        logger.info("[google_tokens] Decrypted access_token for user %s (len=%d)", uid, len(result["accessToken"]))

    return result


async def refresh_google_access_token(refresh_token: str) -> str:
    """Exchange a Google refresh_token for a fresh access_token."""
    logger.info("[google_tokens] Refreshing access_token (refresh_token len=%d)", len(refresh_token))

    client_id = _google_client_id()
    client_secret = _google_client_secret()

    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )

    logger.info(
        "[google_tokens] Token refresh response: HTTP %d, content-type=%s, body_len=%d",
        response.status_code,
        response.headers.get("content-type", "?"),
        len(response.text),
    )

    if response.status_code != 200:
        body = response.text[:500]
        logger.error("[google_tokens] Token refresh FAILED: HTTP %d, body=%s", response.status_code, body)

        error_info = ""
        error_desc = ""
        try:
            payload = response.json()
            error_info = payload.get("error", "")
            error_desc = payload.get("error_description", "")
            logger.error("[google_tokens] Error detail: error=%s, description=%s", error_info, error_desc)
        except Exception:
            pass

        if error_info == "invalid_grant":
            raise ValueError(f"Google refresh token expired or revoked: {error_desc}")

        raise RuntimeError(
            f"Google token refresh failed (HTTP {response.status_code}): {body}"
        )

    data = response.json()
    access_token = data.get("access_token")
    expires_in = data.get("expires_in")
    token_type = data.get("token_type")
    scope = data.get("scope")

    logger.info(
        "[google_tokens] Token refresh OK: token_type=%s, expires_in=%s, scope=%s, access_token_len=%d",
        token_type, expires_in, scope, len(access_token) if access_token else 0,
    )

    if not access_token:
        logger.error("[google_tokens] Token refresh returned no access_token! Full response keys: %s", list(data.keys()))
        raise RuntimeError("Google token refresh returned no access_token")

    return access_token


async def delete_google_tokens(uid: str) -> None:
    logger.info("[google_tokens] Deleting tokens for user %s", uid)
    with get_db() as conn, conn.cursor() as cur:
        cur.execute("delete from google_tokens where user_id = %s", (uid,))
