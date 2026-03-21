"""NB session re-authentication APIs (self-hosted remote browser flow)."""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.middleware.auth import get_current_user
from app.services.db import get_db, serialize_timestamp
from app.services.notebook import derive_nb_session_status, save_nb_session
from app.services.reauth_host import (
    ReauthHostConfigError,
    ReauthHostServiceError,
    create_reauth_session,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/nb-session", tags=["nb_session"])

_ACTIVE_AUTH_STATUSES = {"pending", "running"}


class NBAuthStartResponse(BaseModel):
    sessionId: str
    viewerUrl: str
    status: str
    authFlow: str = "remote_vnc"


class NBAuthPollResponse(BaseModel):
    sessionId: str
    status: str
    viewerUrl: str
    authFlow: str = "remote_vnc"
    error: str | None = None
    completedAt: str | None = None


class NBSessionStatusResponse(BaseModel):
    status: str
    authFlow: str | None = None
    expiresAt: str | None = None
    lastUpdated: str | None = None
    authSession: NBAuthPollResponse | None = None


class NBAuthProviderUpdateRequest(BaseModel):
    sessionId: str
    status: str
    storageState: dict[str, Any] | None = None
    error: str | None = None


def _write_auth_session(uid: str, session_id: str, payload: dict[str, Any]) -> None:
    with get_db() as conn, conn.cursor() as cur:
        cur.execute(
            """
            insert into profiles (id)
            values (%s)
            on conflict (id) do nothing
            """,
            (uid,),
        )
        cur.execute(
            """
            insert into nb_auth_sessions (
                session_id,
                user_id,
                status,
                viewer_url,
                auth_flow,
                started_at,
                updated_at,
                completed_at,
                error,
                nb_session_status,
                expires_at
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (session_id) do update
            set status = excluded.status,
                viewer_url = excluded.viewer_url,
                auth_flow = excluded.auth_flow,
                started_at = coalesce(nb_auth_sessions.started_at, excluded.started_at),
                updated_at = excluded.updated_at,
                completed_at = excluded.completed_at,
                error = excluded.error,
                nb_session_status = excluded.nb_session_status,
                expires_at = excluded.expires_at
            """,
            (
                session_id,
                uid,
                payload.get("status", "pending"),
                payload.get("viewerUrl", ""),
                payload.get("authFlow", "remote_vnc"),
                payload.get("startedAt"),
                payload.get("updatedAt"),
                payload.get("completedAt"),
                payload.get("error"),
                payload.get("nbSessionStatus"),
                payload.get("expiresAt"),
            ),
        )


def _read_auth_session_owner(session_id: str) -> dict[str, Any] | None:
    with get_db() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select user_id, viewer_url, auth_flow
            from nb_auth_sessions
            where session_id = %s
            """,
            (session_id,),
        )
        row = cur.fetchone()

    if not row:
        return None

    return {
        "uid": row["user_id"],
        "viewerUrl": row["viewer_url"],
        "authFlow": row["auth_flow"],
    }


def _read_auth_session(uid: str, session_id: str) -> dict[str, Any] | None:
    with get_db() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select
                session_id,
                status,
                viewer_url,
                auth_flow,
                error,
                completed_at
            from nb_auth_sessions
            where user_id = %s and session_id = %s
            """,
            (uid, session_id),
        )
        row = cur.fetchone()

    if not row:
        return None

    return {
        "sessionId": row["session_id"],
        "status": row["status"],
        "viewerUrl": row["viewer_url"],
        "authFlow": row["auth_flow"],
        "error": row["error"],
        "completedAt": row["completed_at"],
    }


def _read_current_auth_session(uid: str) -> dict[str, Any] | None:
    with get_db() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select
                session_id,
                status,
                viewer_url,
                auth_flow,
                error,
                completed_at
            from nb_auth_sessions
            where user_id = %s
            order by updated_at desc
            limit 1
            """,
            (uid,),
        )
        row = cur.fetchone()

    if not row:
        return None

    return {
        "sessionId": row["session_id"],
        "status": row["status"],
        "viewerUrl": row["viewer_url"],
        "authFlow": row["auth_flow"],
        "error": row["error"],
        "completedAt": row["completed_at"],
    }


def _poll_response(data: dict[str, Any]) -> NBAuthPollResponse:
    status_value = data.get("status", "pending")
    if status_value in _ACTIVE_AUTH_STATUSES:
        status_value = "pending"

    return NBAuthPollResponse(
        sessionId=data["sessionId"],
        status=status_value,
        viewerUrl=data.get("viewerUrl", ""),
        authFlow=data.get("authFlow", "remote_vnc"),
        error=data.get("error"),
        completedAt=serialize_timestamp(data.get("completedAt")),
    )


def _cloud_run_url() -> str:
    value = os.getenv("CLOUD_RUN_URL", "").strip()
    if not value:
        raise ReauthHostConfigError("CLOUD_RUN_URL not configured")
    return value.rstrip("/")


def _callback_token() -> str:
    value = os.getenv("REAUTH_CALLBACK_TOKEN", "").strip()
    if not value:
        raise ReauthHostConfigError("REAUTH_CALLBACK_TOKEN not configured")
    return value


def _callback_url() -> str:
    return f"{_cloud_run_url()}/api/nb-session/internal/update"


def _verify_callback_token(request: Request) -> None:
    auth_header = request.headers.get("Authorization", "")
    if auth_header != f"Bearer {_callback_token()}":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid callback token")


@router.post("/start-auth", response_model=NBAuthStartResponse)
async def start_auth(
    user: dict = Depends(get_current_user),
):
    """Start a self-hosted remote-browser re-auth session and return a viewer URL."""
    uid = user["uid"]

    current = _read_current_auth_session(uid)
    if current and current.get("status") in _ACTIVE_AUTH_STATUSES:
        current_response = _poll_response(current)
        return NBAuthStartResponse(
            sessionId=current_response.sessionId,
            viewerUrl=current_response.viewerUrl,
            status=current_response.status,
            authFlow=current_response.authFlow,
        )

    try:
        session = await create_reauth_session(
            session_id=uuid.uuid4().hex,
            callback_url=_callback_url(),
            callback_token=_callback_token(),
            user=user,
        )
    except ReauthHostConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ReauthHostServiceError as exc:
        raise HTTPException(status_code=502, detail=f"Reauth host init failed: {exc}") from exc

    started_at = datetime.now(timezone.utc)
    _write_auth_session(
        uid,
        session.session_id,
        {
            "status": session.status or "pending",
            "viewerUrl": session.viewer_url,
            "authFlow": session.auth_flow,
            "startedAt": started_at,
            "updatedAt": started_at,
            "error": None,
        },
    )

    return NBAuthStartResponse(
        sessionId=session.session_id,
        viewerUrl=session.viewer_url,
        status=session.status or "pending",
        authFlow=session.auth_flow,
    )


@router.get("/poll/{session_id}", response_model=NBAuthPollResponse)
async def poll_auth_session(
    session_id: str,
    user: dict = Depends(get_current_user),
):
    """Poll a re-auth session started via start-auth."""
    uid = user["uid"]
    data = _read_auth_session(uid, session_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Auth session not found")
    return _poll_response(data)


@router.get("/status", response_model=NBSessionStatusResponse)
async def get_nb_session_status(
    user: dict = Depends(get_current_user),
):
    """Get the current NB session status and whether re-auth is in progress."""
    uid = user["uid"]

    with get_db() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select auth_flow, expires_at, last_updated, status
            from nb_sessions
            where user_id = %s
            """,
            (uid,),
        )
        row = cur.fetchone()

    session_status = "missing"
    auth_flow = None
    expires_at = None
    last_updated = None

    if row:
        auth_flow = row.get("auth_flow")
        expires_at = row.get("expires_at")
        last_updated = row.get("last_updated")
        session_status = derive_nb_session_status(expires_at, row.get("status", ""))

    current = _read_current_auth_session(uid)

    return NBSessionStatusResponse(
        status=session_status,
        authFlow=auth_flow,
        expiresAt=serialize_timestamp(expires_at),
        lastUpdated=serialize_timestamp(last_updated),
        authSession=_poll_response(current) if current else None,
    )


@router.post("/internal/update", include_in_schema=False)
async def update_auth_session_from_provider(
    body: NBAuthProviderUpdateRequest,
    request: Request,
):
    """Trusted callback used by the self-hosted reauth service."""
    _verify_callback_token(request)

    if body.status not in {"completed", "failed", "timed_out"}:
        raise HTTPException(status_code=400, detail="Invalid provider status")

    session = _read_auth_session_owner(body.sessionId)
    if session is None:
        raise HTTPException(status_code=404, detail="Auth session not found")

    uid = session["uid"]
    viewer_url = session.get("viewerUrl", "")
    auth_flow = session.get("authFlow") or "remote_vnc"
    completed_at = datetime.now(timezone.utc)

    if body.status == "completed":
        if not body.storageState:
            raise HTTPException(status_code=400, detail="storageState is required for completed status")

        try:
            session_meta = await save_nb_session(uid, body.storageState, auth_flow=auth_flow)
        except ValueError as exc:
            error_message = str(exc)
            _write_auth_session(
                uid,
                body.sessionId,
                {
                    "status": "failed",
                    "viewerUrl": viewer_url,
                    "authFlow": auth_flow,
                    "updatedAt": completed_at,
                    "completedAt": completed_at,
                    "error": error_message,
                },
            )
            logger.warning("Rejected invalid NB session for user %s session %s: %s", uid, body.sessionId, error_message)
            return {"ok": True}

        _write_auth_session(
            uid,
            body.sessionId,
            {
                "status": "completed",
                "viewerUrl": viewer_url,
                "authFlow": auth_flow,
                "updatedAt": completed_at,
                "completedAt": completed_at,
                "error": None,
                "nbSessionStatus": session_meta["status"],
                "expiresAt": session_meta["expiresAt"],
            },
        )
    else:
        _write_auth_session(
            uid,
            body.sessionId,
            {
                "status": body.status,
                "viewerUrl": viewer_url,
                "authFlow": auth_flow,
                "updatedAt": completed_at,
                "completedAt": completed_at,
                "error": body.error or body.status,
            },
        )
        logger.warning("NB re-auth ended with %s for user %s session %s", body.status, uid, body.sessionId)

    return {"ok": True}
