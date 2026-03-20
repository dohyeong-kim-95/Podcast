"""T-050: User memory API."""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.middleware.auth import get_current_user
from app.services.db import get_db, json_dumps, utc_now

router = APIRouter(prefix="/api", tags=["memory"])


def _normalize_memory(memory: dict[str, Any] | None) -> dict[str, Any]:
    memory = memory or {}
    return {
        "interests": memory.get("interests", ""),
        "tone": memory.get("preferredTone") or memory.get("tone", ""),
        "depth": memory.get("preferredDepth") or memory.get("depth", ""),
        "custom": memory.get("customInstructions") or memory.get("custom", ""),
        "feedbackHistory": memory.get("feedbackHistory", []),
    }


def _serialize_memory(payload: "MemoryPayload") -> dict[str, Any]:
    return {
        "interests": payload.interests,
        "tone": payload.tone,
        "preferredTone": payload.tone,
        "depth": payload.depth,
        "preferredDepth": payload.depth,
        "custom": payload.custom,
        "customInstructions": payload.custom,
    }


class MemoryResponse(BaseModel):
    interests: str = ""
    tone: str = ""
    depth: str = ""
    custom: str = ""
    feedbackHistory: list[dict[str, Any]] = Field(default_factory=list)


class MemoryPayload(BaseModel):
    interests: str = ""
    tone: str = ""
    depth: str = ""
    custom: str = ""


@router.get("/memory", response_model=MemoryResponse)
async def get_memory(user: dict = Depends(get_current_user)):
    uid = user["uid"]
    with get_db() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select interests, tone, depth, custom, feedback_history
            from user_memory
            where user_id = %s
            """,
            (uid,),
        )
        row = cur.fetchone()

    memory = None
    if row:
        memory = {
            "interests": row["interests"],
            "tone": row["tone"],
            "depth": row["depth"],
            "custom": row["custom"],
            "feedbackHistory": row["feedback_history"] or [],
        }
    return MemoryResponse(**_normalize_memory(memory))


@router.put("/memory", response_model=MemoryResponse)
async def update_memory(payload: MemoryPayload, user: dict = Depends(get_current_user)):
    uid = user["uid"]
    serialized = _serialize_memory(payload)
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
            insert into user_memory (
                user_id,
                interests,
                tone,
                depth,
                custom,
                feedback_history,
                updated_at
            )
            values (%s, %s, %s, %s, %s, %s::jsonb, %s)
            on conflict (user_id) do update
            set interests = excluded.interests,
                tone = excluded.tone,
                depth = excluded.depth,
                custom = excluded.custom,
                updated_at = excluded.updated_at
            """,
            (
                uid,
                serialized["interests"],
                serialized["tone"],
                serialized["depth"],
                serialized["custom"],
                json_dumps([]),
                utc_now(),
            ),
        )
        cur.execute(
            """
            select interests, tone, depth, custom, feedback_history
            from user_memory
            where user_id = %s
            """,
            (uid,),
        )
        row = cur.fetchone()

    memory = {
        "interests": row["interests"],
        "tone": row["tone"],
        "depth": row["depth"],
        "custom": row["custom"],
        "feedbackHistory": row["feedback_history"] or [],
    } if row else None
    return MemoryResponse(**_normalize_memory(memory))
