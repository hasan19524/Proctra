"""FastAPI application factory."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app import __version__
from app.api import router as api_router
from app.core.config import settings
from app.core.logging import configure_logging


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )
        # A CSP ships in BOTH environments; production gets a strict policy,
        # development relaxes script/style sources so tooling keeps working.
        if settings.is_production:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: blob:; "
                "font-src 'self' data:; "
                "connect-src 'self' ws: wss:; "
                "media-src 'self' blob:; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self'"
            )
        else:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: blob:; "
                "font-src 'self' data:; "
                "connect-src 'self' ws: wss:; "
                "media-src 'self' blob:; "
                "frame-ancestors 'none';"
            )
        return response


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    # Validate object-storage configuration eagerly (D24 §4): a misconfigured
    # deployment must fail clearly at startup, not on the first upload.
    from app.storage import get_storage

    storage = get_storage()
    # Retention sweeper (D24 §6): sleeps first so startup never races it.
    from app.services.storage_service import retention_sweep_loop

    sweep_task: asyncio.Task[None] | None = None
    if settings.storage_cleanup_interval_hours > 0:
        sweep_task = asyncio.create_task(
            retention_sweep_loop(
                settings.storage_cleanup_interval_hours,
                storage=storage,
            )
        )
    try:
        yield
    finally:
        if sweep_task is not None:
            sweep_task.cancel()
            with suppress(asyncio.CancelledError):
                await sweep_task
        # Close the shared LiveKit SFU client (aiohttp session) on shutdown.
        from app.services.sfu_service import shutdown as sfu_shutdown

        await sfu_shutdown()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        debug=settings.app_debug,
        lifespan=lifespan,
        docs_url="/api/docs" if not settings.is_production else None,
        openapi_url="/api/openapi.json" if not settings.is_production else None,
        redoc_url=None,
    )

    # Only mount TrustedHostMiddleware with explicit, non-wildcard hosts —
    # `["*"]` would silently disable it.
    if settings.is_production and settings.trusted_hosts and "*" not in settings.trusted_hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.backend_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["authorization", "content-type"],
        expose_headers=["X-Request-ID"],
    )

    app.include_router(api_router)
    return app


app = create_app()
