"""Application configuration.

All runtime settings are read from environment variables (optionally via a local
`.env` file). Secrets never live in the repository — see `.env.example`.

The `.env` file is resolved relative to the repository root (not the process
working directory) so that commands run from `backend/` (alembic, pytest, uvicorn)
load the same values as commands run from the root.
"""

import json
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> repository root
REPO_ROOT = Path(__file__).resolve().parents[3]

# Signing/key material that must never reach production (SECURITY.md §7).
_DEV_SECRETS = frozenset(
    {
        "insecure-dev-key-change-me",
        "procto-dev-key",
        "procto-dev-secret",
        "changeme",
        "secret",
    }
)

# Only symmetric/asymmetric HS/RS/ES families PyJWT supports safely. Notably
# excludes ``none`` (which PyJWT accepts when explicitly listed) — a typo in
# JWT_ALGORITHM must not mint universally-valid unsigned tokens.
_ALLOWED_JWT_ALGORITHMS = frozenset({"HS256", "HS384", "HS512", "RS256", "ES256"})


class Settings(BaseSettings):
    """Typed, validated application settings."""

    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- Runtime ----
    app_env: str = Field(default="development", alias="APP_ENV")
    app_debug: bool = Field(default=False, alias="APP_DEBUG")
    app_name: str = "Procto API"
    version: str = "0.1.0"

    # ---- PostgreSQL ----
    database_url: str = Field(
        default="postgresql+asyncpg://procto:procto@localhost:5432/procto",
        alias="DATABASE_URL",
    )

    # ---- Redis ----
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # ---- Auth ----
    secret_key: str = Field(default="insecure-dev-key-change-me", alias="SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_ttl_minutes: int = Field(default=15, alias="ACCESS_TOKEN_TTL_MINUTES")
    refresh_token_ttl_days: int = Field(default=30, alias="REFRESH_TOKEN_TTL_DAYS")

    # ---- LiveKit (SFU) ----
    livekit_url: str = Field(default="ws://localhost:7880", alias="LIVEKIT_URL")
    livekit_api_key: str = Field(default="procto-dev-key", alias="LIVEKIT_API_KEY")
    livekit_api_secret: str = Field(default="procto-dev-secret", alias="LIVEKIT_API_SECRET")

    # ---- CORS / Security ----
    backend_cors_origins: list[str] = Field(
        default=["http://localhost:3001", "http://localhost:3000"],
        alias="BACKEND_CORS_ORIGINS",
    )
    frontend_url: str = Field(default="http://localhost:3001", alias="FRONTEND_URL")
    # Empty by default: only enable TrustedHostMiddleware with explicit hosts.
    trusted_hosts: list[str] = Field(default=[], alias="TRUSTED_HOSTS")
    # Refresh cookie `Secure` flag (SECURITY.md §1). Kept independent of APP_ENV
    # so a mis-set environment cannot silently downgrade the cookie to HTTP.
    # `None` means "follow the environment" (secure in production, off in dev
    # where the app is served over plain http://localhost).
    cookie_secure: bool | None = Field(default=None, alias="COOKIE_SECURE")

    @field_validator("backend_cors_origins", mode="before")
    @classmethod
    def _split_cors(cls, value: object) -> object:
        """Accept either a JSON list or a comma-separated string."""
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("["):
                return json.loads(text)
            return [part.strip() for part in text.split(",") if part.strip()]
        return value

    @field_validator("backend_cors_origins", mode="after")
    @classmethod
    def _cors_no_wildcard(cls, value: list[str]) -> list[str]:
        """Reject ``*``: with allow_credentials=True Starlette mirrors any origin."""
        for origin in value:
            if origin == "*":
                raise ValueError(
                    "BACKEND_CORS_ORIGINS must not contain '*' when credentials are allowed"
                )
            if not origin.startswith(("http://", "https://")):
                raise ValueError(f"invalid CORS origin (expected http(s)://): {origin}")
        return value

    @field_validator("jwt_algorithm", mode="after")
    @classmethod
    def _jwt_algorithm_allowlist(cls, value: str) -> str:
        if value not in _ALLOWED_JWT_ALGORITHMS:
            raise ValueError(
                f"JWT_ALGORITHM must be one of {sorted(_ALLOWED_JWT_ALGORITHMS)}, got {value!r}"
            )
        return value

    @model_validator(mode="after")
    def _reject_insecure_production(self) -> "Settings":
        """Refuse to boot production with dev secrets or debug enabled."""
        if not self.is_production:
            return self
        problems: list[str] = []
        if self.secret_key in _DEV_SECRETS or len(self.secret_key) < 32:
            problems.append("SECRET_KEY is a dev default or shorter than 32 chars")
        if self.livekit_api_key in _DEV_SECRETS or self.livekit_api_secret in _DEV_SECRETS:
            problems.append("LIVEKIT_API_KEY/LIVEKIT_API_SECRET are dev defaults")
        if self.app_debug:
            problems.append("APP_DEBUG must be false in production")
        if problems:
            raise ValueError(
                "Refusing to start in production: " + "; ".join(problems) + ". Set real secrets."
            )
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def refresh_cookie_secure(self) -> bool:
        """Effective `Secure` flag for the refresh cookie."""
        return self.is_production if self.cookie_secure is None else self.cookie_secure


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()


settings = get_settings()
