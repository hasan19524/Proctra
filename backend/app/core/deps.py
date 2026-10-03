"""Shared FastAPI dependencies (current user, optional user, rate limiting)."""

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ratelimit import rate_limit
from app.db import get_session
from app.models.user import User
from app.services.auth_service import get_user_from_token

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Require a valid access token; returns the active user."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await get_user_from_token(session, credentials.credentials)


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User | None:
    """Return the user when a valid token is present, otherwise None."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        return None
    try:
        return await get_user_from_token(session, credentials.credentials)
    except HTTPException:
        return None


async def rate_limit_login(request: Request) -> None:
    """Sliding-window rate limit on login attempts (per IP + per email later)."""
    await rate_limit("login", request.client.host if request.client else "unknown", 10, 60)


async def rate_limit_register(request: Request) -> None:
    """Sliding-window rate limit on registration (per IP)."""
    await rate_limit("register", request.client.host if request.client else "unknown", 5, 60)
