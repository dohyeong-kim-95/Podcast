"""NB session re-authentication APIs (new-tab Browserless flow)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from app.middleware.auth import get_current_user
from app.services.browserless import BrowserlessSession, create_browserless_session, wait_for_notebook_login
from app.services.db import get_db, serialize_timestamp
from app.services.notebook import derive_nb_session_status, save_nb_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/nb-session", tags=["nb_session"])

_ACTIVE_AUTH_STATUSES = {"pending", "running"}


class NBAuthStartResponse(BaseModel):
    sessionId: str
    viewerUrl: str
    status: str
    authFlow: str = "new_tab"


class NBAuthPollResponse(BaseModel):
    sessionId: str
    status: str
    viewerUrl: str
    authFlow: str = "new_tab"
    error: str | None = None
    completedAt: str | None = None


class NBSessionStatusResponse(BaseModel):
    status: str
    authFlow: str | None = None
    expiresAt: str | None = None
    lastUpdated: str | None = None
    authSession: NBAuthPollResponse | None = None


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
                payload.get("authFlow", "new_tab"),
                payload.get("startedAt"),
                payload.get("updatedAt"),
                payload.get("completedAt"),
                payload.get("error"),
                payload.get("nbSessionStatus"),
                payload.get("expiresAt"),
            ),
        )


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
    status = data.get("status", "pending")
    if status in _ACTIVE_AUTH_STATUSES:
        status = "pending"

    return NBAuthPollResponse(
        sessionId=data["sessionId"],
        status=status,
        viewerUrl=data.get("viewerUrl", ""),
        authFlow=data.get("authFlow", "new_tab"),
        error=data.get("error"),
        completedAt=serialize_timestamp(data.get("completedAt")),
    )


async def _run_auth_flow(uid: str, session: BrowserlessSession) -> None:
    now = datetime.now(timezone.utc)
    _write_auth_session(
        uid,
        session.session_id,
        {
            "status": "running",
            "viewerUrl": session.viewer_url,
            "authFlow": "new_tab",
            "updatedAt": now,
            "error": None,
        },
    )

    try:
        storage_state = await wait_for_notebook_login(session)
        session_meta = await save_nb_session(uid, storage_state, auth_flow="new_tab")
        completed_at = datetime.now(timezone.utc)
        _write_auth_session(
            uid,
            session.session_id,
            {
                "status": "completed",
                "viewerUrl": session.viewer_url,
                "authFlow": "new_tab",
                "updatedAt": completed_at,
                "completedAt": completed_at,
                "error": None,
                "nbSessionStatus": session_meta["status"],
                "expiresAt": session_meta["expiresAt"],
            },
        )
    except TimeoutError as exc:
        completed_at = datetime.now(timezone.utc)
        logger.warning("NB re-auth timed out for user %s session %s", uid, session.session_id)
        _write_auth_session(
            uid,
            session.session_id,
            {
                "status": "timed_out",
                "viewerUrl": session.viewer_url,
                "authFlow": "new_tab",
                "updatedAt": completed_at,
                "completedAt": completed_at,
                "error": str(exc),
            },
        )
    except Exception as exc:
        completed_at = datetime.now(timezone.utc)
        logger.exception("NB re-auth failed for user %s session %s", uid, session.session_id)
        _write_auth_session(
            uid,
            session.session_id,
            {
                "status": "failed",
                "viewerUrl": session.viewer_url,
                "authFlow": "new_tab",
                "updatedAt": completed_at,
                "completedAt": completed_at,
                "error": str(exc),
            },
        )


@router.post("/start-auth", response_model=NBAuthStartResponse)
async def start_auth(
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    """Start a Browserless re-auth session and return a new-tab viewer URL."""
    uid = user["uid"]

    current = _read_current_auth_session(uid)
    if current and current.get("status") in _ACTIVE_AUTH_STATUSES:
        current_response = _poll_response(current)
        return NBAuthStartResponse(
            sessionId=current_response.sessionId,
            viewerUrl=current_response.viewerUrl,
            status=current_response.status,
        )

    try:
        session = create_browserless_session()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    started_at = datetime.now(timezone.utc)
    _write_auth_session(
        uid,
        session.session_id,
        {
            "status": "pending",
            "viewerUrl": session.viewer_url,
            "authFlow": "new_tab",
            "startedAt": started_at,
            "updatedAt": started_at,
            "error": None,
        },
    )
    background_tasks.add_task(_run_auth_flow, uid, session)

    return NBAuthStartResponse(
        sessionId=session.session_id,
        viewerUrl=session.viewer_url,
        status="pending",
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

    status = "missing"
    auth_flow = None
    expires_at = None
    last_updated = None

    if row:
        auth_flow = row.get("auth_flow")
        expires_at = row.get("expires_at")
        last_updated = row.get("last_updated")
        status = derive_nb_session_status(expires_at, row.get("status", ""))

    current = _read_current_auth_session(uid)

    return NBSessionStatusResponse(
        status=status,
        authFlow=auth_flow,
        expiresAt=serialize_timestamp(expires_at),
        lastUpdated=serialize_timestamp(last_updated),
        authSession=_poll_response(current) if current else None,
    )
