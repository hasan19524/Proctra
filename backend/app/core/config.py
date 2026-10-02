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

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> repository root
REPO_ROOT = Path(__file__).resolve().parents[3]


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

    # ---- CORS ----
    backend_cors_origins: list[str] = Field(
        default=["http://localhost:3000"],
        alias="BACKEND_CORS_ORIGINS",
    )
    frontend_url: str = Field(default="http://localhost:3000", alias="FRONTEND_URL")

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

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()


settings = get_settings()
