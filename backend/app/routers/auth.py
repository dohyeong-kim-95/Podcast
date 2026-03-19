from fastapi import APIRouter, Depends

from app.middleware.auth import get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/verify")
async def verify(user: dict = Depends(get_current_user)):
    """Firebase ID 토큰을 검증하고 사용자 정보를 반환."""
    return {
        "uid": user.get("uid"),
        "email": user.get("email"),
        "name": user.get("name"),
    }
