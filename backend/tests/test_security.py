"""Unit tests for core security primitives (no infrastructure needed)."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("s3cret-passphrase")
    assert hashed != "s3cret-passphrase"
    assert hashed.startswith("$argon2")
    assert verify_password("s3cret-passphrase", hashed)


def test_wrong_password_rejected() -> None:
    hashed = hash_password("s3cret-passphrase")
    assert not verify_password("different-pass", hashed)


def test_bad_hash_never_raises() -> None:
    # A malformed stored hash must not raise — it simply fails verification.
    assert not verify_password("anything", "not-a-real-hash")


def test_access_token_roundtrip() -> None:
    user_id = uuid4()
    token = create_access_token(user_id, "hasan@procto.dev")
    payload = decode_access_token(token)
    assert payload["sub"] == str(user_id)
    assert payload["email"] == "hasan@procto.dev"
    assert payload["type"] == "access"


def test_expired_access_token_rejected() -> None:
    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "type": "access",
            "exp": datetime.now(UTC) - timedelta(seconds=1),
        },
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(HTTPException) as excinfo:
        decode_access_token(token)
    assert excinfo.value.status_code == 401


def test_tampered_token_rejected() -> None:
    token = create_access_token(uuid4(), "hasan@procto.dev")
    with pytest.raises(HTTPException):
        decode_access_token(token[:-4] + "AAAA")


def test_refresh_tokens_are_unique_and_opaque() -> None:
    first, second = generate_refresh_token(), generate_refresh_token()
    assert first != second
    assert len(first) >= 32
    # Hashing is deterministic and hex-encoded (matches the 64-char column).
    assert hash_refresh_token(first) == hash_refresh_token(first)
    assert len(hash_refresh_token(first)) == 64
