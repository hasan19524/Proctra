"""Redis sliding-window rate limiter (SECURITY.md §3).

Fails OPEN when Redis is unreachable: an outage must not lock every user out of
the product, and the limiter is a defence-in-depth control rather than the sole
barrier. Failures are logged by the caller through the raised-free contract.
"""

import time

from fastapi import HTTPException, status
from redis.exceptions import RedisError

from app.core.redis import get_redis


async def rate_limit(bucket: str, key: str, limit: int, window_seconds: int) -> None:
    """Raise 429 when more than `limit` events occurred in `window_seconds`.

    Implemented as a sorted set of timestamps per (bucket, key).
    """
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
        return  # fail open (availability over strictness for local/dev + outages)

    if count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts, please try again later",
        )
