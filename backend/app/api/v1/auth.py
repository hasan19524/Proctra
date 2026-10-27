"""Authentication routes (Phase 2).

Cookies: the refresh token travels in an httpOnly cookie scoped to
`/api/v1/auth`, so only the auth endpoints can read it. The access token is
returned in the response body and kept in frontend memory.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import (
    get_current_user,
    rate_limit_login,
    rate_limit_logout,
    rate_limit_refresh,
    rate_limit_register,
)
from app.db import get_session
from app.models.user import User
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    UserOut,
)
from app.services import auth_service
from app.services.auth_service import AuthError

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "procto_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth"


def _set_refresh_cookie(response: Response, token: str) -> None:
    """Attach the refresh token as an httpOnly cookie."""
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        max_age=settings.refresh_token_ttl_days * 24 * 60 * 60,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        samesite="lax",
        secure=settings.refresh_cookie_secure,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        samesite="lax",
        secure=settings.refresh_cookie_secure,
    )


def _refresh_token_from_request(request: Request) -> str | None:
    return request.cookies.get(REFRESH_COOKIE)


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(rate_limit_register),
) -> AuthResponse:
    """Create an account and start a session."""
    try:
        auth, refresh = await auth_service.register(
            session, payload.email, payload.password, payload.display_name
        )
    except AuthError as exc:
        await session.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    await session.commit()
    _set_refresh_cookie(response, refresh)
    return auth


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(rate_limit_login),
) -> AuthResponse:
    """Verify credentials and start a session."""
    try:
        auth, refresh = await auth_service.login(session, payload.email, payload.password)
    except AuthError as exc:
        await session.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    await session.commit()
    _set_refresh_cookie(response, refresh)
    return auth


@router.post("/refresh", response_model=AuthResponse)
async def refresh(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(rate_limit_refresh),
) -> AuthResponse:
    """Rotate the refresh token and mint a fresh access token."""
    presented = _refresh_token_from_request(request)
    if not presented:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        auth, refresh_token = await auth_service.refresh_session(session, presented)
    except HTTPException:
        await session.rollback()
        _clear_refresh_cookie(response)
        raise
    await session.commit()
    _set_refresh_cookie(response, refresh_token)
    return auth


@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(rate_limit_logout),
) -> MessageResponse:
    """Revoke the current session (idempotent, works with or without auth)."""
    await auth_service.logout(session, _refresh_token_from_request(request))
    await session.commit()
    _clear_refresh_cookie(response)
    return MessageResponse(message="Signed out")


@router.post("/logout-all", response_model=MessageResponse)
async def logout_all(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MessageResponse:
    """Revoke every session for the current user."""
    await auth_service.logout_all(session, user.id)
    await session.commit()
    return MessageResponse(message="Signed out everywhere")


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    """Current authenticated user."""
    return UserOut.model_validate(user)
