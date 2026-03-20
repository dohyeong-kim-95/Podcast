from __future__ import annotations

import os
from typing import Any

import httpx


def _supabase_url() -> str:
    value = os.getenv("SUPABASE_URL", "").strip()
    if not value:
        raise RuntimeError("SUPABASE_URL not configured")
    return value.rstrip("/")


def _supabase_key() -> str:
    value = (
        os.getenv("SUPABASE_ANON_KEY", "").strip()
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    )
    if not value:
        raise RuntimeError("SUPABASE_ANON_KEY or SUPABASE_SERVICE_ROLE_KEY not configured")
    return value


async def verify_access_token(token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{_supabase_url()}/auth/v1/user",
            headers={
                "apikey": _supabase_key(),
                "Authorization": f"Bearer {token}",
            },
        )
        response.raise_for_status()
        user = response.json()
    metadata = user.get("user_metadata") or {}
    return {
        "uid": user.get("id"),
        "email": user.get("email"),
        "name": metadata.get("full_name") or metadata.get("name"),
        "raw": user,
    }
