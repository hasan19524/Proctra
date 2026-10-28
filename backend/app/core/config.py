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
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

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


def _parse_env_str_list(value: object) -> object:
    """Normalise a list setting arriving as a string.

    Accepts '' (Docker Compose passes it for unset `${VAR:-}` substitutions),
    a JSON list, or a comma-separated list; anything else passes through.
    """
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("["):
            return json.loads(text)
        return [part.strip() for part in text.split(",") if part.strip()]
    return value


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
    # Browser-facing SFU URL handed out by the token endpoint. In production
    # LIVEKIT_URL is rewritten to the internal Docker service
    # (ws://livekit:7880) for server-side room admin — a URL no browser can
    # resolve — so browsers must get this public one instead. Unset = fall
    # back to livekit_url (correct for local dev where they are the same).
    livekit_public_url: str | None = Field(default=None, alias="LIVEKIT_PUBLIC_URL")
    livekit_api_key: str = Field(default="procto-dev-key", alias="LIVEKIT_API_KEY")
    livekit_api_secret: str = Field(default="procto-dev-secret", alias="LIVEKIT_API_SECRET")

    # ---- CORS / Security ----
    # `NoDecode` hands the raw string to the validator below: without it
    # pydantic-settings tries json.loads on every env value for these list
    # fields and raises SettingsError on '' or a comma list (this crashed the
    # production compose, which passes `TRUSTED_HOSTS: ${TRUSTED_HOSTS:-}`).
    backend_cors_origins: Annotated[list[str], NoDecode] = Field(
        default=["http://localhost:3001", "http://localhost:3000"],
        alias="BACKEND_CORS_ORIGINS",
    )
    frontend_url: str = Field(default="http://localhost:3001", alias="FRONTEND_URL")
    # Empty by default: only enable TrustedHostMiddleware with explicit hosts.
    trusted_hosts: Annotated[list[str], NoDecode] = Field(default=[], alias="TRUSTED_HOSTS")
    # Refresh cookie `Secure` flag (SECURITY.md §1). Kept independent of APP_ENV
    # so a mis-set environment cannot silently downgrade the cookie to HTTP.
    # `None` means "follow the environment" (secure in production, off in dev
    # where the app is served over plain http://localhost).
    cookie_secure: bool | None = Field(default=None, alias="COOKIE_SECURE")

    # ---- Object storage (DECISIONS.md D24) ----
    # Provider selection: minio in development/testing, r2 in cloud production.
    # The concrete provider is resolved by app.storage at startup; business
    # logic only ever sees the ObjectStorage interface.
    storage_provider: Literal["minio", "r2"] = Field(default="minio", alias="STORAGE_PROVIDER")
    # MinIO (S3-compatible, local dev/test — no internet or credentials needed).
    minio_endpoint: str = Field(default="localhost:9000", alias="MINIO_ENDPOINT")
    minio_access_key: str = Field(default="minioadmin", alias="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field(default="minioadmin", alias="MINIO_SECRET_KEY")
    minio_bucket: str = Field(default="procto", alias="MINIO_BUCKET")
    minio_secure: bool = Field(default=False, alias="MINIO_SECURE")
    # Cloudflare R2 (S3-compatible cloud storage — production).
    r2_account_id: str = Field(default="", alias="R2_ACCOUNT_ID")
    r2_access_key_id: str = Field(default="", alias="R2_ACCESS_KEY_ID")
    r2_secret_access_key: str = Field(default="", alias="R2_SECRET_ACCESS_KEY")
    r2_bucket: str = Field(default="", alias="R2_BUCKET")
    # Evidence behaviour shared by every provider.
    storage_signed_url_ttl_seconds: int = Field(default=300, alias="STORAGE_SIGNED_URL_TTL_SECONDS")
    # Days until uploaded objects become eligible for automatic cleanup
    # (0 = keep forever). Files under a legal hold are never purged.
    storage_retention_days: int = Field(default=90, alias="STORAGE_RETENTION_DAYS")
    # Hours between retention cleanup runs; 0 disables the background sweeper
    # (tests and tooling can still call purge_expired_files() directly).
    storage_cleanup_interval_hours: int = Field(default=6, alias="STORAGE_CLEANUP_INTERVAL_HOURS")

    @field_validator("backend_cors_origins", mode="before")
    @classmethod
    def _split_cors(cls, value: object) -> object:
        """Accept either a JSON list or a comma-separated string."""
        return _parse_env_str_list(value)

    @field_validator("trusted_hosts", mode="before")
    @classmethod
    def _split_hosts(cls, value: object) -> object:
        """Accept '', a JSON list, or a comma-separated string (see NoDecode)."""
        return _parse_env_str_list(value)

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
