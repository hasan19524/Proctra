"""Health and readiness endpoints.

`/api/health`      → liveness: is the process serving requests? No dependencies.
`/api/health/ready`→ readiness: are Postgres and Redis reachable? Used to verify
                     the local infrastructure is up and, later, container health.
"""

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Response, status

from app import __version__
from app.core.config import settings
from app.core.redis import ping_redis
from app.db import ping_database
from app.schemas.health import HealthResponse, ReadinessResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness probe — cheap, dependency-free."""
    return HealthResponse(
        status="ok",
        service="procto-backend",
        version=__version__,
        environment=settings.app_env,
        time=datetime.now(UTC),
    )


@router.get("/health/ready", response_model=ReadinessResponse)
async def readiness(response: Response) -> ReadinessResponse:
    """Readiness probe — verifies PostgreSQL and Redis connectivity."""
    db_status: Literal["up", "down"] = "up" if await ping_database() else "down"
    redis_status: Literal["up", "down"] = "up" if await ping_redis() else "down"

    ready = db_status == "up" and redis_status == "up"
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        status="ready" if ready else "degraded",
        checks={"database": db_status, "redis": redis_status},
        time=datetime.now(UTC),
    )
