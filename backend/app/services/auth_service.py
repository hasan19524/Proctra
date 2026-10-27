"""Authentication service — business rules live here, not in routers.

Handles: registration, login (uniform errors), refresh rotation with reuse
detection, logout, and loading the current user from an access token.
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models.user import RefreshToken, User
from app.schemas.auth import AuthResponse, UserOut

# Uniform login/register failure — never reveals whether an email exists.
_INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid email or password",
)

# Computed once at import so the unknown-email login path does the same Argon2id
# work as a real verify (closes the ~60 ms timing oracle for account existence).
_DUMMY_PASSWORD_HASH = hash_password("timing-equalizer-not-a-real-password")


class AuthError(Exception):
    """Domain-level auth failure with an HTTP status."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _auth_response(user: User, access_token: str) -> AuthResponse:
    return AuthResponse(
        access_token=access_token,
        expires_in=settings.access_token_ttl_minutes * 60,
        user=UserOut.model_validate(user),
    )


async def _issue_refresh(session: AsyncSession, user_id: uuid.UUID) -> str:
    """Create a refresh token row (hashed) and return the plaintext value."""
    token = generate_refresh_token()
    session.add(
        RefreshToken(
            user_id=user_id,
            token_hash=hash_refresh_token(token),
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_ttl_days),
        )
    )
    await session.flush()
    return token


async def register(
    session: AsyncSession, email: str, password: str, display_name: str
) -> tuple[AuthResponse, str]:
    """Create an account and establish a session.

    Returns (response, refresh_token) — caller sets the cookie.
    """
    existing = await session.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise AuthError(status.HTTP_409_CONFLICT, "An account with this email already exists")

    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name=display_name.strip(),
    )
    session.add(user)
    await session.flush()

    refresh = await _issue_refresh(session, user.id)
    access = create_access_token(user.id, user.email)
    return _auth_response(user, access), refresh


async def login(session: AsyncSession, email: str, password: str) -> tuple[AuthResponse, str]:
    """Verify credentials and establish a session."""
    user = await session.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active:
        # Burn the same Argon2id cost as a real verify so response time does
        # not reveal whether the account exists.
        verify_password(password, _DUMMY_PASSWORD_HASH)
        raise _INVALID_CREDENTIALS  # uniform: unknown email == wrong password
    if not verify_password(password, user.password_hash):
        raise _INVALID_CREDENTIALS

    refresh = await _issue_refresh(session, user.id)
    access = create_access_token(user.id, user.email)
    return _auth_response(user, access), refresh


async def refresh_session(session: AsyncSession, presented: str) -> tuple[AuthResponse, str]:
    """Rotate a refresh token.

    - Unknown token -> 401.
    - Known but revoked -> reuse detected: revoke every session for that user.
    - Expired -> 401 and revoke.
    - Valid -> revoke old row, issue new pair.

    The revoke is an atomic compare-and-swap (``UPDATE ... WHERE revoked_at IS
    NULL ... RETURNING``) so two concurrent requests carrying the same token
    cannot both rotate it into two live sessions.
    """
    token_hash = hash_refresh_token(presented)
    now = datetime.now(UTC)

    claimed = (
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == token_hash, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
            .returning(RefreshToken.user_id, RefreshToken.expires_at)
        )
    ).first()

    if claimed is None:
        # Unknown or already consumed. Distinguish so replay triggers reuse
        # detection (which must survive the caller's rollback — commit here).
        existing = await session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        if existing is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == existing.user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await session.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session revoked")

    user_id, expires_at = claimed

    if expires_at <= now:
        await session.commit()  # persist the revocation before the caller rolls back
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")

    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        await session.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session revoked")

    refresh = await _issue_refresh(session, user.id)
    access = create_access_token(user.id, user.email)
    return _auth_response(user, access), refresh


async def logout(session: AsyncSession, presented: str | None) -> None:
    """Revoke the presented refresh token (idempotent)."""
    if not presented:
        return
    token_hash = hash_refresh_token(presented)
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == token_hash, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await session.flush()


async def logout_all(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Revoke every refresh token for a user (logout everywhere)."""
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await session.flush()


async def get_user_from_token(session: AsyncSession, token: str) -> User:
    """Resolve an access token to an active user, or raise 401."""
    payload = decode_access_token(token)
    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        ) from exc

    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return user
