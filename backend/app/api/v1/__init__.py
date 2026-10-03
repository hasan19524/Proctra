"""Versioned API routers (v1).

Mounts: auth (Phase 2), meetings (Phase 3). Later phases add participants,
chat, notes, history.
"""

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.meetings import router as meetings_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(meetings_router)
