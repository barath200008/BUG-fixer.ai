"""Mirrors: backend/src/common/middleware/auth.middleware.ts"""
from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.errors.app_error import AppError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User


class AuthUser:
    def __init__(self, id: str, email: str, displayName: str, role: str):
        self.id = id
        self.email = email
        self.displayName = displayName
        self.role = role


async def require_auth(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> AuthUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise AppError(401, "AUTH_REQUIRED", "Authentication is required")
    token = authorization[len("Bearer "):].strip()
    try:
        payload = decode_access_token(token)
    except ValueError:
        raise AppError(401, "INVALID_TOKEN", "Authentication token is invalid or expired")

    user = (await db.execute(select(User).where(User.id == payload.get("id")))).scalar_one_or_none()
    if user is None:
        raise AppError(401, "INVALID_TOKEN", "Authentication token is no longer associated with an account")

    return AuthUser(
        id=user.id,
        email=user.email,
        displayName=user.displayName,
        role=user.role.value,
    )


CurrentUser = Depends(require_auth)
