"""API package: aggregates all HTTP routers.

Health lives at `/api/health` (unversioned monitoring endpoint).
Versioned business endpoints live under `/api/v1/`.
"""

from fastapi import APIRouter

from app.api.health import router as health_router
from app.api.v1 import router as v1_router

router = APIRouter()
router.include_router(health_router, prefix="/api", tags=["health"])
router.include_router(v1_router, prefix="/api/v1", tags=["v1"])
