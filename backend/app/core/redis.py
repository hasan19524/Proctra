"""Redis client (application realtime bus, rate limiting, sessions).

Phase 0 only provides connectivity ping; the WS fan-out and rate limiter of
later phases build on this single shared client.
"""

from redis.asyncio import Redis

from app.core.config import settings

_client: Redis | None = None
_pubsub_client: Redis | None = None


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


def get_pubsub_client() -> Redis:
    """Return the Redis client used for WS pub/sub subscriptions.

    Deliberately has **no** ``socket_timeout``: a subscription must be allowed
    to block indefinitely waiting for the next message (the shared client's
    2 s command timeout would kill an idle WS listener).
    """
    global _pubsub_client
    if _pubsub_client is None:
        _pubsub_client = Redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=2,
        )
    return _pubsub_client


async def ping_redis() -> bool:
    """Cheap connectivity check used by the readiness endpoint."""
    try:
        return bool(await get_redis().ping())
    except Exception:
        return False


async def close_redis() -> None:
    """Close the shared clients on application shutdown."""
    global _client, _pubsub_client
    if _client is not None:
        await _client.aclose()
        _client = None
    if _pubsub_client is not None:
        await _pubsub_client.aclose()
        _pubsub_client = None
