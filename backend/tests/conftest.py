"""Shared pytest fixtures.

Integration tests run against real infrastructure:
- PostgreSQL: separate `procto_test` database (created on demand)
- Redis: dedicated logical database index 15

Environment overrides happen at import time (before the app is imported) so
`app.core.config.Settings` resolves to the test infrastructure.
"""

import os
from collections.abc import AsyncIterator

# --- Environment overrides (must run before any `app.*` import) ------------
TEST_DB_NAME = "procto_test"
os.environ["DATABASE_URL"] = f"postgresql+asyncpg://procto:procto@localhost:5434/{TEST_DB_NAME}"
os.environ["REDIS_URL"] = "redis://localhost:6380/15"
os.environ["APP_ENV"] = "development"
os.environ["APP_DEBUG"] = "false"

import asyncpg  # type: ignore[import-untyped]  # noqa: E402
import pytest  # noqa: E402
from alembic.config import Config as AlembicConfig  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from alembic import command  # noqa: E402

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ensure_test_database() -> None:
    """Create the test database if it does not exist yet."""

    async def _create() -> None:
        conn = await asyncpg.connect(
            host="localhost",
            port=5434,
            user="procto",
            password="procto",
            database="postgres",
        )
        try:
            exists = await conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1", TEST_DB_NAME
            )
            if not exists:
                await conn.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
        finally:
            await conn.close()

    import asyncio

    asyncio.run(_create())


def _run_migrations() -> None:
    """Apply alembic migrations to the test database (idempotent)."""
    cfg = AlembicConfig(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "alembic"))
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session", autouse=True)
def test_infrastructure() -> None:
    """Create the test database and run migrations once per session."""
    _ensure_test_database()
    _run_migrations()


@pytest.fixture(autouse=True)
async def clean_state() -> AsyncIterator[None]:
    """Truncate domain tables and flush the rate-limit keys before each test."""
    from sqlalchemy import text

    from app.core.redis import get_redis
    from app.db import engine

    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE refresh_tokens, users RESTART IDENTITY CASCADE"))

    redis = get_redis()
    keys = [key async for key in redis.scan_iter("ratelimit:*")]
    if keys:
        await redis.delete(*keys)

    yield


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """HTTP client wired to the FastAPI app (cookie jar preserved)."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client
