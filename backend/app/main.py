"""FastAPI application factory.

Phase 0 scope: app wiring only (config, CORS, logging, routers, health).
Meeting/auth/WS functionality arrives in later phases.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import router as api_router
from app.core.config import settings
from app.core.logging import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown hooks (DB pools, Redis, WS registries arrive later)."""
    configure_logging()
    yield


def create_app() -> FastAPI:
    """Build the FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        debug=settings.app_debug,
        lifespan=lifespan,
        docs_url="/api/docs" if not settings.is_production else None,
        openapi_url="/api/openapi.json" if not settings.is_production else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.backend_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)
    return app


app = create_app()
