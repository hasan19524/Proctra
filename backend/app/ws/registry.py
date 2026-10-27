"""In-memory connection registry for one worker process (REALTIME.md §1).

Cross-worker delivery goes through Redis pub/sub; this registry only tracks
sockets owned by *this* process. Ephemeral by design — never persisted.
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.websockets import WebSocket

# Max concurrent sockets one user may hold in a single meeting on this worker.
# Bounds the authenticated-connection DoS (each socket holds a Redis pubsub
# subscription, a presence refcount, and an attendance row).
MAX_CONNS_PER_USER_IN_MEETING = 3


@dataclass(slots=True)
class LocalConnection:
    """One accepted WebSocket in this worker."""

    conn_id: str
    meeting_code: str
    user_id: str
    websocket: "WebSocket"
    is_host: bool = False
    closed: bool = False
    # Queued in the waiting room: no presence/attendance until admitted, and
    # only WAITING_VISIBLE_FRAMES reach this socket (Phase 13).
    waiting: bool = False
    # Set by host kick/end paths so the target's receive loop unwinds promptly
    # even when the ASGI server won't deliver a disconnect to a pending receive.
    kick: "asyncio.Event" = field(default_factory=asyncio.Event)


class ConnectionRegistry:
    """Thread-unsafe (asyncio single-thread) registry keyed by conn id."""

    def __init__(self) -> None:
        self._by_conn: dict[str, LocalConnection] = {}
        # (meeting_code, user_id) -> live connection count for that user.
        self._user_counts: dict[tuple[str, str], int] = {}

    def add(
        self,
        meeting_code: str,
        user_id: str,
        websocket: "WebSocket",
        *,
        is_host: bool = False,
    ) -> LocalConnection:
        conn = LocalConnection(
            conn_id=str(uuid.uuid4()),
            meeting_code=meeting_code,
            user_id=user_id,
            websocket=websocket,
            is_host=is_host,
        )
        self._by_conn[conn.conn_id] = conn
        key = (meeting_code, user_id)
        self._user_counts[key] = self._user_counts.get(key, 0) + 1
        return conn

    def remove(self, conn: LocalConnection) -> bool:
        """Drop the connection; returns True when it was the user's last one."""
        self._by_conn.pop(conn.conn_id, None)
        key = (conn.meeting_code, conn.user_id)
        remaining = self._user_counts.get(key, 0) - 1
        if remaining > 0:
            self._user_counts[key] = remaining
            return False
        self._user_counts.pop(key, None)
        return True

    def get(self, conn_id: str) -> LocalConnection | None:
        """Look up one local connection by id."""
        return self._by_conn.get(conn_id)

    def at_capacity(self, meeting_code: str, user_id: str) -> bool:
        """True when the user already holds the max sockets in this meeting."""
        return self._user_counts.get((meeting_code, user_id), 0) >= MAX_CONNS_PER_USER_IN_MEETING

    def in_meeting(self, meeting_code: str) -> list[LocalConnection]:
        """All live local connections for a meeting."""
        return [
            c for c in self._by_conn.values() if c.meeting_code == meeting_code and not c.closed
        ]

    def count(self, meeting_code: str) -> int:
        return len(self.in_meeting(meeting_code))

    def local_user_ids(self, meeting_code: str) -> set[str]:
        """Distinct users with at least one local connection in the meeting."""
        return {c.user_id for c in self.in_meeting(meeting_code)}


_registry: ConnectionRegistry | None = None


def get_registry() -> ConnectionRegistry:
    """Process-wide registry singleton."""
    global _registry
    if _registry is None:
        _registry = ConnectionRegistry()
    return _registry
