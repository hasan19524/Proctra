"""Waiting-room decision flags, kept in Redis (SECURITY.md 3, Phase 13).

A join decision outlives one socket: the flag lets an approved user's
reconnect skip the queue within a short window, and a rejection is visible
to that user's serve loop even when the rejecting host lives on another
worker (the flag is the cross-worker signal; the registry is per-process).
"""

import time

from app.core.redis import get_redis

# Short memory: approvals are per-visit, not memberships (SECURITY.md 3).
WAIT_DECISION_TTL_SECONDS = 5 * 60

APPROVED = "approved"
REJECTED = "rejected"


def _key(meeting_code: str, user_id: str) -> str:
    return f"ws:meeting:{meeting_code}:wait:{user_id}"


async def set_decision(meeting_code: str, user_id: str, decision: str) -> None:
    redis = get_redis()
    await redis.set(_key(meeting_code, user_id), decision, ex=WAIT_DECISION_TTL_SECONDS)


async def get_decision(meeting_code: str, user_id: str) -> str | None:
    raw = await get_redis().get(_key(meeting_code, user_id))
    return raw.decode() if isinstance(raw, bytes) else raw


async def clear_decision(meeting_code: str, user_id: str) -> None:
    await get_redis().delete(_key(meeting_code, user_id))


def now_ms() -> int:
    """Monotonic-ish helper for client-facing timestamps."""
    return int(time.time() * 1000)
