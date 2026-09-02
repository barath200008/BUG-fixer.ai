"""Mirrors: backend/src/common/middleware/auth.middleware.ts"""
from fastapi import Depends, Header

from app.common.errors.app_error import AppError
from app.core.security import decode_access_token


class AuthUser:
    def __init__(self, id: str, email: str, displayName: str, role: str):
        self.id = id
        self.email = email
        self.displayName = displayName
        self.role = role


async def require_auth(authorization: str | None = Header(default=None)) -> AuthUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise AppError(401, "AUTH_REQUIRED", "Authentication is required")
    token = authorization[len("Bearer "):].strip()
    try:
        payload = decode_access_token(token)
    except ValueError:
        raise AppError(401, "INVALID_TOKEN", "Authentication token is invalid or expired")
    return AuthUser(
        id=payload["id"],
        email=payload["email"],
        displayName=payload["displayName"],
        role=payload["role"],
    )


CurrentUser = Depends(require_auth)
