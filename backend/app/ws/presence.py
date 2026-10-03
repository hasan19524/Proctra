"""Ephemeral per-meeting presence state, kept in Redis (REALTIME.md §1).

Presence is a read-model for the UI: who is connected and their flags. It is
never written to Postgres (ARCHITECTURE.md §5); history tables arrive later.
"""

import json
import time
from typing import Any

from app.core.redis import get_redis

# Sliding expiry so presence keys never outlive a crashed worker by much.
PRESENCE_TTL_SECONDS = 6 * 60 * 60


def _presence_key(meeting_code: str) -> str:
    return f"ws:meeting:{meeting_code}:presence"


def _refcount_key(meeting_code: str, user_id: str) -> str:
    return f"ws:meeting:{meeting_code}:refcount:{user_id}"


def _now_ms() -> int:
    return int(time.time() * 1000)


async def retain_user(meeting_code: str, user_id: str) -> int:
    """Bump the cross-worker connection count for a user in a meeting."""
    redis = get_redis()
    key = _refcount_key(meeting_code, user_id)
    count = int(await redis.incr(key))
    await redis.expire(key, PRESENCE_TTL_SECONDS)
    return count


async def release_user(meeting_code: str, user_id: str) -> bool:
    """Drop one connection count; True when the user is fully gone."""
    redis = get_redis()
    key = _refcount_key(meeting_code, user_id)
    remaining = int(await redis.decr(key))
    if remaining > 0:
        return False
    await redis.delete(key)
    await redis.hdel(_presence_key(meeting_code), user_id)
    return True


async def upsert_presence(
    meeting_code: str,
    user_id: str,
    *,
    name: str,
    is_host: bool,
    flags: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create or refresh a participant's presence entry; returns the entry."""
    entry: dict[str, Any] = {
        "user_id": user_id,
        "name": name,
        "is_host": is_host,
        "mic_on": True,
        "camera_on": True,
        "hand_raised": False,
        "screen_share_on": False,
        "joined_at": _now_ms(),
    }
    if flags:
        entry.update(flags)
    redis = get_redis()
    key = _presence_key(meeting_code)
    await redis.hset(key, user_id, json.dumps(entry))
    await redis.expire(key, PRESENCE_TTL_SECONDS)
    return entry


async def update_flags(
    meeting_code: str, user_id: str, flags: dict[str, Any]
) -> dict[str, Any] | None:
    """Merge flag changes into an existing entry; None when absent."""
    redis = get_redis()
    key = _presence_key(meeting_code)
    raw = await redis.hget(key, user_id)
    if raw is None:
        return None
    entry: dict[str, Any] = json.loads(raw)
    allowed = {"mic_on", "camera_on", "hand_raised", "screen_share_on"}
    # Ignore anything that is not a real boolean rather than trusting it.
    entry.update({k: v for k, v in flags.items() if k in allowed and isinstance(v, bool)})
    await redis.hset(key, user_id, json.dumps(entry))
    await redis.expire(key, PRESENCE_TTL_SECONDS)
    return entry


async def remove_presence(meeting_code: str, user_id: str) -> None:
    """Drop a participant's entry directly (used by meeting-ended cleanup)."""
    redis = get_redis()
    await redis.hdel(_presence_key(meeting_code), user_id)
    await redis.delete(_refcount_key(meeting_code, user_id))


async def get_presence(meeting_code: str) -> list[dict[str, Any]]:
    """All presence entries for a meeting, host first then join order."""
    redis = get_redis()
    raw = await redis.hgetall(_presence_key(meeting_code))
    entries = [json.loads(value) for value in raw.values()]
    entries.sort(key=lambda e: (not e.get("is_host", False), e.get("joined_at", 0)))
    return entries


async def clear_presence(meeting_code: str) -> None:
    """Remove the whole meeting presence hash (meeting ended)."""
    await get_redis().delete(_presence_key(meeting_code))
