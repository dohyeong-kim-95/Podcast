from fastapi import APIRouter, Depends

from app.middleware.auth import get_current_user
from app.services.notifications import upsert_user_profile

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/verify")
async def verify(user: dict = Depends(get_current_user)):
    """Supabase access token을 검증하고 사용자 정보를 반환."""
    uid = user.get("uid")
    upsert_user_profile(uid, user.get("email"), user.get("name"))

    return {
        "uid": uid,
        "email": user.get("email"),
        "name": user.get("name"),
    }
