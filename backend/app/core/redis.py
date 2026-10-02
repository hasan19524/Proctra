"""Redis client (application realtime bus, rate limiting, sessions).

Phase 0 only provides connectivity ping; the WS fan-out and rate limiter of
later phases build on this single shared client.
"""

from redis.asyncio import Redis

from app.core.config import settings

_client: Redis | None = None


def get_redis() -> Redis:
    """Return the shared async Redis client, creating it on first use."""
    global _client
    if _client is None:
        _client = Redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    return _client


async def ping_redis() -> bool:
    """Cheap connectivity check used by the readiness endpoint."""
    try:
        return bool(await get_redis().ping())
    except Exception:
        return False


async def close_redis() -> None:
    """Close the shared client on application shutdown."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
