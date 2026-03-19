"""T-050: User memory API."""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.middleware.auth import get_current_user
from app.services.firebase import get_firestore_client

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
    db = get_firestore_client()
    doc = db.collection("users").document(uid).get()
    memory = doc.to_dict().get("memory") if doc.exists else None
    return MemoryResponse(**_normalize_memory(memory))


@router.put("/memory", response_model=MemoryResponse)
async def update_memory(payload: MemoryPayload, user: dict = Depends(get_current_user)):
    uid = user["uid"]
    db = get_firestore_client()
    user_ref = db.collection("users").document(uid)
    user_ref.set({"memory": _serialize_memory(payload)}, merge=True)

    doc = user_ref.get()
    memory = doc.to_dict().get("memory") if doc.exists else None
    return MemoryResponse(**_normalize_memory(memory))
