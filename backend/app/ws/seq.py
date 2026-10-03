"""Per-meeting monotonic sequence for durable events (REALTIME.md §1).

Stored in Redis so every worker agrees on ordering; ``seq`` is attached to
durable frames (chat in Phase 5) and drives reconnect replay.
"""

from app.core.redis import get_redis


def _seq_key(meeting_code: str) -> str:
    return f"ws:meeting:{meeting_code}:seq"


async def current_seq(meeting_code: str) -> int:
    """The last assigned sequence for a meeting (0 when none yet)."""
    raw = await get_redis().get(_seq_key(meeting_code))
    return int(raw) if raw else 0


async def next_seq(meeting_code: str) -> int:
    """Allocate the next sequence number (durable events only)."""
    value = await get_redis().incr(_seq_key(meeting_code))
    return int(value)
