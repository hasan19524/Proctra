"""Database access: async engine, session factory, health ping."""

from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    connect_args={
        "timeout": 3,  # asyncpg connect timeout (seconds)
        "command_timeout": 5,  # asyncpg statement timeout (seconds)
    },
)

SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a scoped async session."""
    async with SessionLocal() as session:
        yield session


async def ping_database() -> bool:
    """Cheap connectivity check used by the readiness endpoint."""
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        return False
    return True


async def dispose_engine() -> None:
    """Release the connection pool (application shutdown)."""
    await engine.dispose()
