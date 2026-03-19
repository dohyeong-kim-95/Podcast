"""NB session re-authentication APIs (new-tab Browserless flow)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from app.middleware.auth import get_current_user
from app.services.browserless import BrowserlessSession, create_browserless_session, wait_for_notebook_login
from app.services.firebase import get_firestore_client
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


def _serialize_timestamp(value: Any) -> str | None:
    if value and hasattr(value, "isoformat"):
        normalized = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return normalized.isoformat()
    return None


def _session_doc_refs(uid: str, session_id: str):
    db = get_firestore_client()
    base = db.collection("users").document(uid).collection("nb_auth_sessions")
    return base.document(session_id), base.document("current")


def _write_auth_session(uid: str, session_id: str, payload: dict[str, Any]) -> None:
    session_ref, current_ref = _session_doc_refs(uid, session_id)
    session_ref.set(payload, merge=True)
    current_ref.set({"sessionId": session_id, **payload}, merge=True)


def _read_auth_session(uid: str, session_id: str) -> dict[str, Any] | None:
    session_ref, _ = _session_doc_refs(uid, session_id)
    doc = session_ref.get()
    if not doc.exists:
        return None
    return {"sessionId": doc.id, **doc.to_dict()}


def _read_current_auth_session(uid: str) -> dict[str, Any] | None:
    db = get_firestore_client()
    doc = db.collection("users").document(uid).collection("nb_auth_sessions").document("current").get()
    if not doc.exists:
        return None
    data = doc.to_dict()
    session_id = data.get("sessionId")
    if not session_id:
        return None
    return {"sessionId": session_id, **data}


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
        completedAt=_serialize_timestamp(data.get("completedAt")),
    )


async def _run_auth_flow(uid: str, session: BrowserlessSession) -> None:
    _write_auth_session(
        uid,
        session.session_id,
        {
            "status": "running",
            "viewerUrl": session.viewer_url,
            "authFlow": "new_tab",
            "updatedAt": datetime.now(timezone.utc),
            "error": None,
        },
    )

    try:
        storage_state = await wait_for_notebook_login(session)
        session_meta = await save_nb_session(uid, storage_state, auth_flow="new_tab")
        _write_auth_session(
            uid,
            session.session_id,
            {
                "status": "completed",
                "viewerUrl": session.viewer_url,
                "authFlow": "new_tab",
                "updatedAt": datetime.now(timezone.utc),
                "completedAt": datetime.now(timezone.utc),
                "error": None,
                "nbSessionStatus": session_meta["status"],
                "expiresAt": session_meta["expiresAt"],
            },
        )
    except TimeoutError as exc:
        logger.warning("NB re-auth timed out for user %s session %s", uid, session.session_id)
        _write_auth_session(
            uid,
            session.session_id,
            {
                "status": "timed_out",
                "viewerUrl": session.viewer_url,
                "authFlow": "new_tab",
                "updatedAt": datetime.now(timezone.utc),
                "completedAt": datetime.now(timezone.utc),
                "error": str(exc),
            },
        )
    except Exception as exc:
        logger.exception("NB re-auth failed for user %s session %s", uid, session.session_id)
        _write_auth_session(
            uid,
            session.session_id,
            {
                "status": "failed",
                "viewerUrl": session.viewer_url,
                "authFlow": "new_tab",
                "updatedAt": datetime.now(timezone.utc),
                "completedAt": datetime.now(timezone.utc),
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
    db = get_firestore_client()
    doc = db.collection("users").document(uid).collection("nb_session").document("current").get()

    status = "missing"
    auth_flow = None
    expires_at = None
    last_updated = None

    if doc.exists:
        data = doc.to_dict()
        auth_flow = data.get("authFlow")
        expires_at = data.get("expiresAt")
        last_updated = data.get("lastUpdated")
        status = derive_nb_session_status(expires_at, data.get("status", ""))

    current = _read_current_auth_session(uid)
    auth_in_progress = bool(current and current.get("status") in _ACTIVE_AUTH_STATUSES)

    return NBSessionStatusResponse(
        status=status,
        authFlow=auth_flow,
        expiresAt=_serialize_timestamp(expires_at),
        lastUpdated=_serialize_timestamp(last_updated),
        authSession=_poll_response(current) if current else None,
    )
