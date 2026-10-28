"""Versioned API routers (v1).

Mounts: auth (Phase 2), meetings (Phase 3), app WebSocket gateway (Phase 4),
files (Phase 17 — object storage). Later phases add history.
"""

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.files import router as files_router
from app.api.v1.meetings import router as meetings_router
from app.ws.gateway import router as ws_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(meetings_router)
router.include_router(files_router)
router.include_router(ws_router, prefix="/ws", tags=["ws"])
