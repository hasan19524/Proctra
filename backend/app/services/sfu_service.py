"""LiveKit SFU enforcement (SECURITY.md — defence in depth).

The app WebSocket only governs *application* state (presence, chat, notes). A
removed or kicked participant could otherwise keep publishing audio/video to the
LiveKit room because nothing told the SFU to drop them. This module closes that
gap: host ``remove`` and meeting ``end`` also evict the participant (or close the
room) at the media layer.

Calls are fire-and-forget from the gateway: an SFU outage must never block or
fail the app-layer action that already committed. Failures are logged, not raised.
"""

import asyncio
import logging

from livekit import api as livekit_api

from app.core.config import settings

logger = logging.getLogger(__name__)

# Shared async client (aiohttp session). Created lazily on first use so import
# never opens a network connection, and reused to avoid a session per call.
_client: livekit_api.LiveKitAPI | None = None
_client_lock = asyncio.Lock()

# Strong references to in-flight fire-and-forget SFU tasks (prevents GC).
_background: "set[asyncio.Task[None]]" = set()


async def _get_client() -> livekit_api.LiveKitAPI:
    global _client
    if _client is None:
        async with _client_lock:
            if _client is None:
                _client = livekit_api.LiveKitAPI(
                    settings.livekit_url,
                    settings.livekit_api_key,
                    settings.livekit_api_secret,
                )
    return _client


async def sfu_remove_participant(room: str, identity: str) -> None:
    """Evict one participant from the LiveKit room (blocking call).

    Raises on failure — callers should schedule this via `spawn_*` so the error
    is logged rather than propagated.
    """
    client = await _get_client()
    await client.room.remove_participant(
        livekit_api.RoomParticipantIdentity(room=room, identity=identity)
    )


async def sfu_close_room(room: str) -> None:
    """Close the LiveKit room entirely (blocking call)."""
    client = await _get_client()
    await client.room.delete_room(livekit_api.DeleteRoomRequest(room=room))


async def _guarded(coro, label: str) -> None:  # type: ignore[no-untyped-def]
    """Await an SFU coroutine, logging (never raising) any failure."""
    try:
        await coro
    except Exception:
        logger.warning("SFU enforcement failed (%s)", label, exc_info=True)


def _spawn(coro, label: str) -> None:  # type: ignore[no-untyped-def]
    """Run an SFU coroutine in the background, holding a reference so the task
    is not garbage-collected mid-flight (RUF006). Failures are logged only."""
    task = asyncio.create_task(_guarded(coro, label))
    _background.add(task)
    task.add_done_callback(_background.discard)


def spawn_remove_participant(room: str, identity: str) -> None:
    """Schedule an SFU eviction without awaiting it (never blocks the caller)."""
    _spawn(sfu_remove_participant(room, identity), f"remove {identity}@{room}")


def spawn_close_room(room: str) -> None:
    """Schedule an SFU room close without awaiting it (never blocks the caller)."""
    _spawn(sfu_close_room(room), f"close {room}")


async def shutdown() -> None:
    """Close the shared aiohttp session (called on app shutdown)."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
