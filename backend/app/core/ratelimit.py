"""Redis sliding-window rate limiter (SECURITY.md §3).

Fails OPEN when Redis is unreachable: an outage must not lock every user out of
the product, and the limiter is a defence-in-depth control rather than the sole
barrier. Fail-open is logged loudly so an outage that disables brute-force
protection is never silent.
"""

import logging
import time

from fastapi import HTTPException, status
from redis.exceptions import RedisError

from app.core.redis import get_redis

logger = logging.getLogger(__name__)


_last_fail_open_log = 0.0
_FAIL_OPEN_LOG_INTERVAL = 30.0  # seconds; avoid log spam during a sustained outage


async def rate_limit(bucket: str, key: str, limit: int, window_seconds: int) -> None:
    """Raise 429 when more than `limit` events occurred in `window_seconds`.

    Implemented as a sorted set of timestamps per (bucket, key).
    """
    global _last_fail_open_log
    redis_key = f"ratelimit:{bucket}:{key}"
    now = time.time()
    cutoff = now - window_seconds

    try:
        redis = get_redis()
        pipe = redis.pipeline()
        pipe.zremrangebyscore(redis_key, 0, cutoff)
        pipe.zadd(redis_key, {str(now): now})
        pipe.zcard(redis_key)
        pipe.expire(redis_key, window_seconds + 1)
        results = await pipe.execute()
        count = int(results[2])
    except RedisError:
        # Fail open (availability over strictness) but never silently: an outage
        # disables brute-force protection and must be observable.
        if now - _last_fail_open_log >= _FAIL_OPEN_LOG_INTERVAL:
            _last_fail_open_log = now
            logger.warning(
                "rate limiter unavailable (bucket=%s) — failing OPEN", bucket, exc_info=True
            )
        return

    if count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts, please try again later",
        )
