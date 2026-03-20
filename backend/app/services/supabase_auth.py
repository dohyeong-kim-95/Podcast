from __future__ import annotations

import os
from typing import Any

import httpx


class InvalidAccessTokenError(Exception):
    pass


class AuthVerificationServiceError(Exception):
    pass


def _normalize_env_value(value: str) -> str:
    return value.strip().replace("\r", "").replace("\n", "").strip("'\"")


def _supabase_url() -> str:
    value = _normalize_env_value(os.getenv("SUPABASE_URL", ""))
    if not value:
        raise RuntimeError("SUPABASE_URL not configured")
    return value.rstrip("/")


def _supabase_auth_key() -> str:
    value = (
        _normalize_env_value(os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""))
        or _normalize_env_value(os.getenv("SUPABASE_ANON_KEY", ""))
    )
    if not value:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY or SUPABASE_ANON_KEY not configured")
    return value


async def verify_access_token(token: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{_supabase_url()}/auth/v1/user",
                headers={
                    "apikey": _supabase_auth_key(),
                    "Authorization": f"Bearer {token}",
                },
            )
    except httpx.TimeoutException as exc:
        raise AuthVerificationServiceError("Supabase auth verification timed out") from exc
    except httpx.HTTPError as exc:
        raise AuthVerificationServiceError("Supabase auth verification request failed") from exc

    if response.status_code in {401, 403}:
        raise InvalidAccessTokenError("Invalid or expired token")
    if response.is_error:
        raise AuthVerificationServiceError(
            f"Supabase auth verification failed with status {response.status_code}"
        )

    user = response.json()
    metadata = user.get("user_metadata") or {}
    return {
        "uid": user.get("id"),
        "email": user.get("email"),
        "name": metadata.get("full_name") or metadata.get("name"),
        "raw": user,
    }
