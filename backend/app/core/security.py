"""Password hashing, JWT access tokens and opaque refresh tokens.

Security decisions (SECURITY.md §1):
- Argon2id password hashing (memory-hard, modern default).
- Access token: signed JWT, short expiry, held in frontend memory.
- Refresh token: opaque random string delivered in an httpOnly cookie and stored
  only as a SHA-256 hash in Postgres (rotated on every use, revocable).
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import HTTPException, status

from app.core.config import settings

# Argon2id parameters: 64 MiB memory, 2 passes, 1 lane — OWASP-recommended floor.
_hasher = PasswordHasher(time_cost=2, memory_cost=64 * 1024, parallelism=1)


def hash_password(plain: str) -> str:
    """Hash a plaintext password with Argon2id."""
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a password against its Argon2id hash (never raises on bad hash)."""
    try:
        return _hasher.verify(hashed, plain)
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_access_token(user_id: uuid.UUID, email: str) -> str:
    """Mint a short-lived signed JWT access token."""
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "type": "access",
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_ttl_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate an access token.

    Raises HTTPException 401 on any invalid/expired token.
    """
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired"
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        ) from exc

    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
    return payload


def generate_refresh_token() -> str:
    """Return a new opaque refresh token (never stored in plaintext)."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    """SHA-256 hex digest of the refresh token for storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
