from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx


DEFAULT_NB_AUTH_URL = "https://notebooklm.google.com"


class ReauthHostConfigError(RuntimeError):
    pass


class ReauthHostServiceError(RuntimeError):
    pass


@dataclass(frozen=True)
class HostedReauthSession:
    session_id: str
    viewer_url: str
    status: str
    auth_flow: str
    expires_at: datetime | None = None


def _normalize_env_value(value: str) -> str:
    return value.strip().replace("\r", "").replace("\n", "").strip("'\"")


def _required_env(name: str) -> str:
    value = _normalize_env_value(os.getenv(name, ""))
    if not value:
        raise ReauthHostConfigError(f"{name} not configured")
    return value


def _reauth_host_base_url() -> str:
    return _required_env("REAUTH_HOST_BASE_URL").rstrip("/")


def _reauth_host_api_key() -> str:
    return _required_env("REAUTH_HOST_API_KEY")


def _nb_auth_target_url() -> str:
    return _normalize_env_value(os.getenv("NB_AUTH_TARGET_URL", DEFAULT_NB_AUTH_URL)) or DEFAULT_NB_AUTH_URL


def _nb_auth_timeout_seconds() -> int:
    raw = _normalize_env_value(os.getenv("NB_AUTH_TIMEOUT_SECONDS", "300")) or "300"
    try:
        return max(60, int(raw))
    except ValueError as exc:
        raise ReauthHostConfigError(f"Invalid NB_AUTH_TIMEOUT_SECONDS={raw!r}") from exc


def _request_timeout_seconds() -> float:
    raw = _normalize_env_value(os.getenv("REAUTH_HOST_REQUEST_TIMEOUT_SECONDS", "20")) or "20"
    try:
        return max(1.0, float(raw))
    except ValueError as exc:
        raise ReauthHostConfigError(f"Invalid REAUTH_HOST_REQUEST_TIMEOUT_SECONDS={raw!r}") from exc


def _parse_error_message(response: httpx.Response) -> str:
    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            payload = response.json()
            if isinstance(payload, dict):
                detail = payload.get("detail")
                if detail:
                    return str(detail)
        except ValueError:
            pass

    text = response.text.strip()
    if text:
        return text
    return f"Reauth host returned HTTP {response.status_code}"


async def create_reauth_session(
    *,
    session_id: str,
    callback_url: str,
    callback_token: str,
    user: dict[str, Any],
) -> HostedReauthSession:
    payload = {
        "sessionId": session_id,
        "targetUrl": _nb_auth_target_url(),
        "ttlSeconds": _nb_auth_timeout_seconds(),
        "callbackUrl": callback_url,
        "callbackToken": callback_token,
        "userId": user.get("uid"),
        "userEmail": user.get("email"),
        "userName": user.get("name"),
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(_request_timeout_seconds())) as client:
        response = await client.post(
            f"{_reauth_host_base_url()}/internal/sessions",
            headers={"Authorization": f"Bearer {_reauth_host_api_key()}"},
            json=payload,
        )

    if response.status_code >= 400:
        raise ReauthHostServiceError(_parse_error_message(response))

    try:
        data = response.json()
    except ValueError as exc:
        raise ReauthHostServiceError("Reauth host returned invalid JSON") from exc

    expires_at = None
    raw_expires_at = data.get("expiresAt")
    if isinstance(raw_expires_at, str) and raw_expires_at:
        try:
            expires_at = datetime.fromisoformat(raw_expires_at.replace("Z", "+00:00"))
        except ValueError:
            expires_at = None

    return HostedReauthSession(
        session_id=data.get("sessionId") or session_id,
        viewer_url=str(data.get("viewerUrl") or ""),
        status=str(data.get("status") or "pending"),
        auth_flow=str(data.get("authFlow") or "remote_vnc"),
        expires_at=expires_at,
    )
