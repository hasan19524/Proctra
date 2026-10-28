"""Application WebSocket gateway (Phases 4-8).

Connect handshake (auth + meeting authorization), versioned envelope loop,
heartbeat/idle handling, Redis pub/sub fan-out, durable chat (persist to
Postgres first, then broadcast — REALTIME.md §1/§3), host controls, shared
notes, and transient reactions (whitelisted labels, never persisted).
"""

import asyncio
import contextlib
import json
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.core.ratelimit import rate_limit
from app.core.redis import get_pubsub_client, get_redis
from app.core.security import verify_password
from app.db import SessionLocal
from app.models.meeting import Meeting
from app.models.message import MAX_BODY_LENGTH
from app.models.note import MAX_NOTE_CONTENT_CHARS, VISIBILITIES, VISIBILITY_HOST_ONLY
from app.models.proctor import SIGNAL_TYPES
from app.models.user import User
from app.services import sfu_service
from app.services.audit_service import audit
from app.services.auth_service import get_user_from_token
from app.services.meeting_service import (
    MeetingNotFoundError,
    get_meeting_by_code,
    normalize_code,
)
from app.services.message_service import (
    create_message,
    list_messages_after,
    list_recent_messages,
    message_dto,
)
from app.services.note_service import list_notes, note_dto, upsert_note
from app.services.participant_service import record_join, record_leave
from app.services.proctor_service import flag_out, list_recent_flags, record_event
from app.ws import presence
from app.ws.envelope import (
    CLOSE_FORBIDDEN,
    CLOSE_IDLE_TIMEOUT,
    CLOSE_NOT_FOUND,
    CLOSE_PROTOCOL_ERROR,
    CLOSE_UNAUTHORIZED,
    ProtocolError,
    parse_client_frame,
    server_frame,
)
from app.ws.registry import get_registry
from app.ws.seq import current_seq, next_seq
from app.ws.waiting import APPROVED, REJECTED, get_decision, set_decision

if TYPE_CHECKING:
    from app.ws.registry import LocalConnection

logger = logging.getLogger(__name__)

router = APIRouter()

# The client pings every 25 s (REALTIME.md); no frame for this long = dead peer.
IDLE_TIMEOUT_SECONDS = 60.0
# Upper bound for one reconnect replay (the snapshot also carries a 50-msg tail).
REPLAY_LIMIT = 500
# Join budget per (user, meeting) per minute: bounds meeting-password guessing
# (SECURITY.md §4) while leaving plenty for reconnect churn.
JOIN_RATE = (15, 60)
# Pre-auth handshake budget per IP: bounds token brute-force / connection floods
# before any DB or Argon2 work happens.
HANDSHAKE_RATE = (30, 60)
# Per-connection inbound frame budget (sustained frames/sec, burst). Bounds
# chat/reaction/sync amplification from a single socket.
FLOOD_RATE_PER_SECOND = 8.0
FLOOD_BURST = 40.0
# Frames a queued (waiting-room) connection may see: nothing about meeting
# content leaks before the host admits them (SECURITY.md §6).
WAITING_VISIBLE_FRAMES = frozenset(
    {"waiting.approved", "waiting.rejected", "meeting.ended", "meeting.locked"}
)
# Transient reactions are a closed set (matches the frontend ReactionBar).
REACTION_LABELS = frozenset(
    {"Heart", "Thumbs up", "Party", "Clap", "Laugh", "Wow", "Sad", "Angry", "Thumbs down"}
)


class _Kicked(Exception):
    """The connection was kicked by a host action (remove/end)."""


class _TokenBucket:
    """Simple monotonic token bucket for per-connection flood control."""

    __slots__ = ("_burst", "_last", "_rate", "_tokens")

    def __init__(self, rate: float, burst: float) -> None:
        self._rate = rate
        self._burst = burst
        self._tokens = burst
        self._last = time.monotonic()

    def allow(self) -> bool:
        now = time.monotonic()
        self._tokens = min(self._burst, self._tokens + (now - self._last) * self._rate)
        self._last = now
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False


def _channel(meeting_code: str) -> str:
    return f"ws:meeting:{meeting_code}"


async def _reject(websocket: WebSocket, close_code: int, err_code: str, message: str) -> None:
    """Accept, send a machine-readable error frame, then close."""
    try:
        await websocket.accept()
        await websocket.send_text(
            server_frame("error", {"code": err_code, "message": message, "retryable": False})
        )
        await websocket.close(code=close_code)
    except (RuntimeError, WebSocketDisconnect):
        # Peer vanished mid-handshake; nothing else to do.
        pass


async def _send(websocket: WebSocket, frame_text: str) -> None:
    with contextlib.suppress(RuntimeError, WebSocketDisconnect):
        await websocket.send_text(frame_text)


def _is_host_only_note(frame_text: str) -> bool:
    """True when this broadcast frame carries a host-only notes document."""
    if '"note.updated"' not in frame_text:
        return False
    try:
        payload = json.loads(frame_text).get("payload") or {}
    except (ValueError, TypeError, AttributeError):
        return False
    return isinstance(payload, dict) and payload.get("visibility") == VISIBILITY_HOST_ONLY


def _is_host_only_frame(frame_text: str) -> bool:
    """True when a broadcast frame must never reach a non-host connection.

    Covers host-only notes (Phase 7) and proctoring flag fan-out (Phase 16 —
    a student's cheating score is private to the host, never broadcast).
    """
    if '"proctor.flag"' in frame_text:
        return True
    return _is_host_only_note(frame_text)


def _frame_type(frame_text: str) -> str | None:
    """Best-effort event type of a serialized frame (malformed -> None)."""
    try:
        parsed = json.loads(frame_text)
    except (ValueError, TypeError):
        return None
    frame_type = parsed.get("type") if isinstance(parsed, dict) else None
    return frame_type if isinstance(frame_type, str) else None


async def _deliver(conn: "LocalConnection", frame_text: str) -> None:
    """Send one broadcast frame to a local connection, honoring visibility."""
    if _is_host_only_frame(frame_text) and not conn.is_host:
        return
    if conn.waiting and _frame_type(frame_text) not in WAITING_VISIBLE_FRAMES:
        return
    await _send(conn.websocket, frame_text)


async def _broadcast(meeting_code: str, frame_text: str) -> None:
    """Publish a frame to every worker (and thus every connection) in the meeting."""
    try:
        await get_redis().publish(_channel(meeting_code), frame_text)
    except Exception:
        registry = get_registry()
        for conn in registry.in_meeting(meeting_code):
            await _deliver(conn, frame_text)


async def _relay(websocket: WebSocket, meeting_code: str, conn_id: str, pubsub: Any) -> None:
    """Relay frames from an already-subscribed Redis pub/sub to one socket."""
    try:
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            data = message.get("data")
            if not isinstance(data, str):
                continue
            conn = get_registry().get(conn_id)
            if conn is None or conn.closed:
                break
            if _is_host_only_frame(data) and not conn.is_host:
                continue
            if conn.waiting and _frame_type(data) not in WAITING_VISIBLE_FRAMES:
                continue
            await _send(websocket, data)
    except asyncio.CancelledError:
        raise
    except Exception:
        pass


async def _snapshot(meeting_code: str, meeting: Meeting, user_id: str) -> str:
    """Build the ``sync.state`` full snapshot frame (roster, chat tail, notes)."""
    participants = await presence.get_presence(meeting_code)
    is_host = str(meeting.host_id) == user_id
    async with SessionLocal() as session:
        row = await session.get(Meeting, meeting.id)
        recent = await list_recent_messages(session, meeting.id)
        notes = await list_notes(session, meeting.id, include_host_only=is_host)
        proctor_rows = await list_recent_flags(session, meeting.id, limit=200) if is_host else []
    current = row or meeting  # re-read so lock/permission changes are visible
    payload: dict[str, Any] = {
        "meeting": {
            "code": current.code,
            "title": current.title,
            "status": current.status,
            "kind": current.kind,
            "is_locked": current.is_locked,
            "allow_chat": current.allow_chat,
            "allow_reactions": current.allow_reactions,
            "allow_screen_share": current.allow_screen_share,
            "proctoring_enabled": current.proctoring_enabled,
        },
        "self": {"user_id": user_id},
        "participants": participants,
        "messages": [message_dto(message, sender) for message, sender in recent],
        "notes": [note_dto(note, name) for note, name in notes],
        "seq": await current_seq(meeting_code),
    }
    if is_host and proctor_rows:
        # Host-only: recent proctoring flags so a late-joining host sees history.
        payload["proctor_flags"] = [
            flag_out(event, name).model_dump(mode="json") for event, name in proctor_rows
        ]
    return server_frame("sync.state", payload)


async def _replay_chat(websocket: WebSocket, meeting: Meeting, last_seq: int) -> None:
    """Re-send durable chat frames with ``seq > last_seq`` (REALTIME.md §3).

    ``last_seq == 0`` means a fresh join — the snapshot's tail already carries
    recent history, so only true reconnects trigger a Postgres replay.
    """
    if last_seq <= 0:
        return
    async with SessionLocal() as session:
        missed = await list_messages_after(session, meeting.id, last_seq, limit=REPLAY_LIMIT)
    for message, sender in missed:
        await _send(
            websocket,
            server_frame("chat.message", message_dto(message, sender), seq=message.seq),
        )


def _parse_uuid(value: object) -> uuid.UUID | None:
    if isinstance(value, str):
        try:
            return uuid.UUID(value)
        except ValueError:
            return None
    return None


async def _handle_chat_send(
    websocket: WebSocket,
    meeting_code: str,
    meeting: Meeting,
    user: User,
    frame: Any,
) -> None:
    """Persist a chat message (idempotent per ``client_id``), then broadcast."""
    payload = frame.payload if isinstance(frame.payload, dict) else {}
    body = payload.get("body")
    body = body.strip() if isinstance(body, str) else ""
    if not body or len(body) > MAX_BODY_LENGTH:
        await _send(
            websocket,
            server_frame(
                "error",
                {
                    "code": "invalid_message",
                    "message": f"Message body must be 1-{MAX_BODY_LENGTH} characters",
                    "retryable": False,
                },
            ),
        )
        return

    client_id = payload.get("client_id")
    if not isinstance(client_id, str) or not client_id.strip():
        client_id = None
    reply_to = _parse_uuid(payload.get("reply_to"))

    seq = await next_seq(meeting_code)
    try:
        async with SessionLocal() as session:
            row = await session.get(Meeting, meeting.id)
            if row is not None and not row.allow_chat:
                await _send(
                    websocket,
                    server_frame(
                        "error",
                        {
                            "code": "permission_denied",
                            "message": "Chat is turned off by the host",
                            "retryable": False,
                        },
                    ),
                )
                return
            message, _created = await create_message(
                session,
                meeting_id=meeting.id,
                sender_id=user.id,
                sender_name=user.display_name,
                body=body,
                seq=seq,
                client_id=client_id,
                reply_to=reply_to,
            )
    except Exception:
        await _send(
            websocket,
            server_frame(
                "error",
                {
                    "code": "internal_error",
                    "message": "Could not save the message",
                    "retryable": True,
                },
            ),
        )
        return

    # Broadcast even on idempotent retries: at-least-once delivery.
    await _broadcast(
        meeting_code,
        server_frame("chat.message", message_dto(message, user.display_name), seq=message.seq),
    )


async def _handle_reaction_send(
    websocket: WebSocket,
    meeting_code: str,
    meeting: Meeting,
    user: User,
    frame: Any,
) -> None:
    """Broadcast one transient reaction; never persisted, no ``seq``."""
    payload = frame.payload if isinstance(frame.payload, dict) else {}
    label = payload.get("label")
    if not isinstance(label, str) or label not in REACTION_LABELS:
        await _send_ws_error(websocket, "invalid_reaction", "Unknown reaction label")
        return
    async with SessionLocal() as session:
        row = await session.get(Meeting, meeting.id)
        if row is not None and not row.allow_reactions:
            await _send_ws_error(
                websocket, "permission_denied", "Reactions are turned off by the host"
            )
            return
    await _broadcast(
        meeting_code,
        server_frame(
            "reaction.received",
            {"user_id": str(user.id), "name": user.display_name, "label": label},
        ),
    )


async def _handle_note_save(
    websocket: WebSocket,
    meeting_code: str,
    meeting: Meeting,
    user: User,
    frame: Any,
) -> None:
    """Persist one notes document (whole-content replace), then broadcast.

    ``host_only`` documents are host-only in both directions: only the host
    may save one, and non-hosts never receive one in ``sync.state``.
    """
    payload = frame.payload if isinstance(frame.payload, dict) else {}
    visibility = payload.get("visibility", "all")
    if visibility not in VISIBILITIES:
        await _send_ws_error(websocket, "invalid_note", "visibility must be all or host_only")
        return
    content = payload.get("content")
    if not isinstance(content, dict):
        await _send_ws_error(websocket, "invalid_note", "content must be a JSON object")
        return
    if len(json.dumps(content)) > MAX_NOTE_CONTENT_CHARS:
        await _send_ws_error(
            websocket, "invalid_note", f"Note must be at most {MAX_NOTE_CONTENT_CHARS} characters"
        )
        return
    if visibility == VISIBILITY_HOST_ONLY and str(meeting.host_id) != str(user.id):
        await _send_ws_error(websocket, "permission_denied", "Host role required")
        return

    try:
        async with SessionLocal() as session:
            note = await upsert_note(
                session,
                meeting_id=meeting.id,
                visibility=visibility,
                content=content,
                updated_by=user.id,
            )
    except Exception:
        await _send_ws_error(websocket, "internal_error", "Could not save the note", retryable=True)
        return

    await _broadcast(
        meeting_code,
        server_frame("note.updated", note_dto(note, user.display_name)),
    )


# Proctor events per (user, meeting) per minute: bounds a tampered client
# flooding fake flags without starving the 8 fps flood bucket.
PROCTOR_RATE = (30, 60)


async def _handle_proctor_event(
    websocket: WebSocket,
    meeting_code: str,
    meeting: Meeting,
    user: User,
    frame: Any,
) -> None:
    """Persist one proctoring observation and fan the flag out to the host.

    The sender is always the subject — a client can never flag another user.
    Points and the meeting minute are computed server-side (proctor_service),
    never taken from the client. Hosts are exempt: the vision model only
    watches participants, not the proctor.
    """
    if meeting.kind != "exam" or not meeting.proctoring_enabled:
        await _send_ws_error(websocket, "not_proctored", "This meeting is not a proctored exam")
        return
    if str(meeting.host_id) == str(user.id):
        # The host is the proctor, not a subject; silently ignore.
        return

    payload = frame.payload if isinstance(frame.payload, dict) else {}
    signal = payload.get("signal")
    if not isinstance(signal, str) or signal not in SIGNAL_TYPES:
        await _send_ws_error(websocket, "invalid_signal", "Unknown proctor signal")
        return

    try:
        await rate_limit("proctor_event", f"{user.id}:{meeting_code}", *PROCTOR_RATE)
    except HTTPException:
        await _send_ws_error(
            websocket, "rate_limited", "Too many proctoring events", retryable=True
        )
        return

    try:
        async with SessionLocal() as session:
            event = await record_event(
                session,
                meeting=meeting,
                user=user,
                signal=signal,
                duration_s=payload.get("duration_s", 0.0),
                detail=payload.get("detail"),
            )
            await session.commit()
    except Exception:
        await _send_ws_error(
            websocket,
            "internal_error",
            "Could not record the proctoring event",
            retryable=True,
        )
        return

    await _broadcast(
        meeting_code,
        server_frame(
            "proctor.flag",
            flag_out(event, user.display_name).model_dump(mode="json"),
        ),
    )


async def _send_ws_error(
    websocket: WebSocket, code: str, message: str, *, retryable: bool = False
) -> None:
    await _send(
        websocket,
        server_frame("error", {"code": code, "message": message, "retryable": retryable}),
    )


async def _handle_host_action(
    websocket: WebSocket,
    meeting_code: str,
    meeting: Meeting,
    user: User,
    frame: Any,
    conn: "LocalConnection",
) -> None:
    """Host-only controls: lock/end, mute/remove participants, permissions.

    The caller's role is re-derived from Postgres on every action
    (SECURITY.md — never trust the in-memory handshake copy).
    """
    payload = frame.payload if isinstance(frame.payload, dict) else {}
    action = payload.get("action")
    registry = get_registry()

    async with SessionLocal() as session:
        fresh = await session.get(Meeting, meeting.id)
        if fresh is None:
            await _send_ws_error(websocket, "not_found", "Meeting no longer exists")
            return
        if str(fresh.host_id) != str(user.id):
            await _send_ws_error(websocket, "forbidden", "Host role required")
            return

        if action == "lock" or action == "unlock":
            fresh.is_locked = action == "lock"
            await audit(
                session,
                meeting_id=fresh.id,
                actor_id=user.id,
                action=action,
                detail={"is_locked": fresh.is_locked},
            )
            await session.commit()
            meeting.is_locked = fresh.is_locked
            await _broadcast(
                meeting_code,
                server_frame("meeting.locked", {"is_locked": fresh.is_locked}),
            )
            return

        if action == "end":
            if fresh.status != "ended":
                fresh.status = "ended"
                fresh.ended_at = datetime.now(UTC)
                await audit(session, meeting_id=fresh.id, actor_id=user.id, action="end")
                await session.commit()
            meeting.status = "ended"
            # Evict everyone at the SFU too — otherwise LiveKit keeps streaming.
            sfu_service.spawn_close_room(meeting_code)
            local = list(registry.in_meeting(meeting_code))
            # Direct send first: terminal frames must not race the close.
            for target in local:
                await _send(target.websocket, server_frame("meeting.ended", {}))
            for target in local:
                target.closed = True
                target.kick.set()
                await _close(target.websocket, CLOSE_FORBIDDEN, "meeting_ended")
            # Other workers learn via pub/sub (local sockets already got it).
            await _broadcast(meeting_code, server_frame("meeting.ended", {}))
            return

        if action == "mute_participant":
            target_id = payload.get("target_id")
            if not isinstance(target_id, str) or not target_id:
                await _send_ws_error(websocket, "invalid_target", "target_id is required")
                return
            present = {p.get("user_id") for p in await presence.get_presence(meeting_code)}
            if target_id not in present:
                await _send_ws_error(websocket, "invalid_target", "Participant not in the meeting")
                return
            await audit(
                session,
                meeting_id=fresh.id,
                actor_id=user.id,
                action="mute_participant",
                target_id=_parse_uuid(target_id),
            )
            await session.commit()
            await _broadcast(
                meeting_code,
                server_frame(
                    "participant.muted",
                    {"user_id": target_id, "by_user_id": str(user.id)},
                ),
            )
            return

        if action == "remove":
            target_id = payload.get("target_id")
            if not isinstance(target_id, str) or not target_id:
                await _send_ws_error(websocket, "invalid_target", "target_id is required")
                return
            if target_id == str(user.id):
                await _send_ws_error(websocket, "invalid_target", "Cannot remove yourself")
                return
            targets = [c for c in registry.in_meeting(meeting_code) if c.user_id == target_id]
            if not targets:
                await _send_ws_error(websocket, "invalid_target", "Participant not in the meeting")
                return
            await audit(
                session,
                meeting_id=fresh.id,
                actor_id=user.id,
                action="remove",
                target_id=_parse_uuid(target_id),
            )
            await session.commit()
            # Evict from the SFU so the removed user stops publishing media too.
            sfu_service.spawn_remove_participant(meeting_code, target_id)
            for target in targets:
                await _send(
                    target.websocket,
                    server_frame("participant.removed", {"user_id": target_id}),
                )
                target.closed = True
                target.kick.set()
                await _close(target.websocket, CLOSE_FORBIDDEN, "removed")
            # Cross-worker copies of the target close themselves on this frame.
            await _broadcast(
                meeting_code,
                server_frame("participant.removed", {"user_id": target_id}),
            )
            return

        if action == "set_permissions":
            changed = False
            for field in ("allow_chat", "allow_reactions", "allow_screen_share"):
                value = payload.get(field)
                if isinstance(value, bool) and getattr(fresh, field) != value:
                    setattr(fresh, field, value)
                    changed = True
            if changed:
                await audit(
                    session,
                    meeting_id=fresh.id,
                    actor_id=user.id,
                    action="set_permissions",
                    detail={
                        "allow_chat": fresh.allow_chat,
                        "allow_reactions": fresh.allow_reactions,
                        "allow_screen_share": fresh.allow_screen_share,
                    },
                )
                await session.commit()
                meeting.allow_chat = fresh.allow_chat
                meeting.allow_reactions = fresh.allow_reactions
                meeting.allow_screen_share = fresh.allow_screen_share
            await _broadcast(
                meeting_code,
                server_frame(
                    "permission.changed",
                    {
                        "allow_chat": fresh.allow_chat,
                        "allow_reactions": fresh.allow_reactions,
                        "allow_screen_share": fresh.allow_screen_share,
                    },
                ),
            )
            return

        if action in ("approve", "reject"):
            target_id = payload.get("target_id")
            if not isinstance(target_id, str) or not target_id:
                await _send_ws_error(websocket, "invalid_target", "target_id is required")
                return
            if target_id == str(user.id):
                await _send_ws_error(websocket, "invalid_target", "Cannot decide on yourself")
                return
            target_uuid = _parse_uuid(target_id)
            waiting_here = any(
                c.user_id == target_id and c.waiting for c in registry.in_meeting(meeting_code)
            )
            if not waiting_here and await get_decision(meeting_code, target_id) is None:
                # Phantom-id guard: no live request on this worker and no prior
                # decision. (Waiting sockets on *other* workers aren't visible
                # to this per-process registry; deployment is single-worker.)
                await _send_ws_error(websocket, "invalid_target", "No join request to decide on")
                return
            if action == "approve":
                if fresh.status == "ended":
                    await _send_ws_error(websocket, "not_found", "Meeting has ended")
                    return
                await set_decision(meeting_code, target_id, APPROVED)
            else:
                await set_decision(meeting_code, target_id, REJECTED)
            await audit(
                session,
                meeting_id=fresh.id,
                actor_id=user.id,
                action="waiting_approve" if action == "approve" else "waiting_reject",
                target_id=target_uuid,
            )
            await session.commit()

            if action == "reject":
                # Local waiters are closed here: terminal frame first, then
                # the close (D16); remote workers learn from the flag/frames.
                for target in [
                    c
                    for c in registry.in_meeting(meeting_code)
                    if c.user_id == target_id and c.waiting
                ]:
                    await _send(
                        target.websocket,
                        server_frame("waiting.rejected", {"user_id": target_id}),
                    )
                    target.closed = True
                    target.kick.set()
                    await _close(target.websocket, CLOSE_FORBIDDEN, "rejected")
            await _broadcast(
                meeting_code,
                server_frame(
                    "waiting.approved" if action == "approve" else "waiting.rejected",
                    {"user_id": target_id},
                ),
            )
            logger.info(
                "meeting=%s user=%s action=%s target=%s", meeting_code, user.id, action, target_id
            )
            return

        await _send_ws_error(websocket, "unknown_action", f"Unsupported host action: {action}")


@router.websocket("/meetings/{meeting_code}")
async def ws_meeting(
    websocket: WebSocket,
    meeting_code: str,
    token: str | None = Query(default=None),
    password: str | None = Query(default=None, max_length=64),
) -> None:
    """Authenticated app-WS endpoint for one meeting (REALTIME.md §1)."""
    code = normalize_code(meeting_code)

    # 0. Origin allow-list: browsers always send Origin on a WS upgrade, so a
    #    cross-site page cannot dial into a meeting on a victim's session.
    origin = websocket.headers.get("origin")
    if origin and origin not in settings.backend_cors_origins and origin != settings.frontend_url:
        await _reject(websocket, CLOSE_PROTOCOL_ERROR, "origin_not_allowed", "Origin not allowed")
        return

    # 0.5 Pre-auth handshake budget per IP: bounds token brute-force and
    #     connection floods before any DB or Argon2 work happens.
    try:
        await rate_limit(
            "ws_handshake",
            websocket.client.host if websocket.client else "unknown",
            *HANDSHAKE_RATE,
        )
    except HTTPException:
        await _reject(websocket, CLOSE_PROTOCOL_ERROR, "rate_limited", "Too many connections")
        return

    # 1. Authenticate the upgrade (access token as query param).
    if not token:
        await _reject(websocket, CLOSE_UNAUTHORIZED, "unauthorized", "Missing access token")
        return

    # DB session lives only for the handshake — never for the socket's life.
    async with SessionLocal() as session:
        try:
            user = await get_user_from_token(session, token)
        except HTTPException:
            await _reject(websocket, CLOSE_UNAUTHORIZED, "unauthorized", "Invalid access token")
            return

        try:
            meeting = await get_meeting_by_code(session, code)
        except MeetingNotFoundError:
            await _reject(websocket, CLOSE_NOT_FOUND, "not_found", "Meeting not found")
            return

        is_host = str(meeting.host_id) == str(user.id)

    # 2. Authorize against the meeting state.
    if meeting.status == "ended":
        await _reject(websocket, CLOSE_FORBIDDEN, "meeting_ended", "Meeting has ended")
        return
    if meeting.is_locked and not is_host:
        await _reject(websocket, CLOSE_FORBIDDEN, "meeting_locked", "Meeting is locked")
        return

    # 3. Join budget per (user, meeting): bounds meeting-password guessing.
    try:
        await rate_limit("ws_join", f"{user.id}:{code}", *JOIN_RATE)
    except HTTPException:
        await _reject(websocket, CLOSE_PROTOCOL_ERROR, "rate_limited", "Too many join attempts")
        return

    # 4. Meeting password (host bypasses; D23).
    if (
        meeting.password_hash is not None
        and not is_host
        and (not password or not verify_password(password, meeting.password_hash))
    ):
        err_code = "wrong_password" if password else "meeting_password_required"
        await _reject(websocket, CLOSE_FORBIDDEN, err_code, "Meeting password required")
        return

    # 5. Waiting room: a non-host joins into a queue unless already admitted.
    awaiting = False
    if meeting.waiting_room and not is_host:
        decision = await get_decision(code, str(user.id))
        if decision == REJECTED:
            await _reject(websocket, CLOSE_FORBIDDEN, "meeting_rejected", "Join rejected")
            return
        awaiting = decision != APPROVED

    # 5.5 Connection cap: one user may hold only a few sockets per meeting.
    registry = get_registry()
    if registry.at_capacity(code, str(user.id)):
        await _reject(
            websocket, CLOSE_FORBIDDEN, "too_many_connections", "Too many open connections"
        )
        return

    await websocket.accept()

    conn = registry.add(code, str(user.id), websocket, is_host=is_host)
    conn.waiting = awaiting

    # 6. Presence + fan-out subscription before anything is announced.
    #    Subscribe first: a broadcast published before the subscription is
    #    active would be silently lost.
    pubsub = get_pubsub_client().pubsub()
    await pubsub.subscribe(_channel(code))
    listener = asyncio.create_task(_relay(websocket, code, conn.conn_id, pubsub))

    if awaiting:
        # Queued: no presence row, no attendance row, no roster snapshot.
        await _send(websocket, server_frame("waiting.state", {"approved": False}))
        await _broadcast(
            code,
            server_frame(
                "join.request",
                {"user_id": str(user.id), "name": user.display_name},
            ),
        )
    else:
        await presence.retain_user(code, str(user.id))
        await presence.upsert_presence(
            code,
            str(user.id),
            name=user.display_name,
            is_host=is_host,
        )
        async with SessionLocal() as session:
            await record_join(
                session,
                meeting_id=meeting.id,
                user_id=user.id,
                role="host" if is_host else "participant",
            )

        # Handshake snapshot, then announce the join to everyone.
        await _send(websocket, await _snapshot(code, meeting, str(user.id)))
        await _broadcast(
            code,
            server_frame(
                "participant.joined",
                {"user_id": str(user.id), "name": user.display_name, "is_host": is_host},
            ),
        )
        await _broadcast(
            code,
            server_frame("presence.state", {"participants": await presence.get_presence(code)}),
        )

    try:
        await _serve(websocket, code, meeting, user, conn)
    finally:
        conn.closed = True
        listener.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await listener
        with contextlib.suppress(Exception):
            # redis.asyncio's aclose is untyped in this release.
            await cast(Any, pubsub).aclose()
        registry.remove(conn)
        # A connection that was never admitted (still queued) has no presence
        # refcount and no attendance row: there is nothing to release.
        if not conn.waiting:
            became_gone = await presence.release_user(code, str(user.id))
            if became_gone:
                with contextlib.suppress(Exception):
                    async with SessionLocal() as session:
                        await record_leave(session, meeting_id=meeting.id, user_id=user.id)
                await _broadcast(
                    code,
                    server_frame("participant.left", {"user_id": str(user.id)}),
                )
            await _broadcast(
                code,
                server_frame("presence.state", {"participants": await presence.get_presence(code)}),
            )


async def _receive_frame(websocket: WebSocket, conn: "LocalConnection") -> str:
    """Next client text frame, the idle timeout, or a kick.

    A pending ``receive()`` is not woken when *we* close the socket (the ASGI
    server only injects a disconnect on the client's handshake), so host kicks
    race it explicitly — otherwise presence/attendance cleanup stalls.
    """
    recv_task = asyncio.create_task(websocket.receive_text())
    kick_task = asyncio.create_task(conn.kick.wait())
    try:
        done, _ = await asyncio.wait(
            {recv_task, kick_task},
            timeout=IDLE_TIMEOUT_SECONDS,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if not done:
            raise TimeoutError("idle timeout")
        if recv_task in done:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                kick_task.cancel()
                await kick_task
            return recv_task.result()  # may raise WebSocketDisconnect/RuntimeError
        with contextlib.suppress(asyncio.CancelledError, Exception):
            recv_task.cancel()
            await recv_task
        raise _Kicked()
    finally:
        for task in (recv_task, kick_task):
            if not task.done():
                task.cancel()


async def _promote(
    websocket: WebSocket,
    meeting_code: str,
    meeting: Meeting,
    user: User,
    conn: "LocalConnection",
) -> None:
    """Admit a queued connection: presence, attendance, fan-out (Phase 13).

    Runs on the waiter's own worker when their client re-syncs after seeing
    ``waiting.approved`` — the Redis decision flag is the cross-worker signal
    (D23), the promotion happens exactly where the socket lives, so only one
    worker ever announces the join.
    """
    conn.waiting = False
    is_host = str(meeting.host_id) == str(user.id)
    await presence.retain_user(meeting_code, str(user.id))
    await presence.upsert_presence(
        meeting_code,
        str(user.id),
        name=user.display_name,
        is_host=is_host,
    )
    async with SessionLocal() as session:
        await record_join(
            session,
            meeting_id=meeting.id,
            user_id=user.id,
            role="host" if is_host else "participant",
        )
    await _broadcast(
        meeting_code,
        server_frame(
            "participant.joined",
            {"user_id": str(user.id), "name": user.display_name, "is_host": is_host},
        ),
    )
    await _broadcast(
        meeting_code,
        server_frame("presence.state", {"participants": await presence.get_presence(meeting_code)}),
    )
    logger.info("meeting=%s user=%s waiting room admitted", meeting_code, user.id)


async def _serve(
    websocket: WebSocket,
    meeting_code: str,
    meeting: Meeting,
    user: User,
    conn: "LocalConnection",
) -> None:
    """Receive loop: parse envelopes, dispatch, keep the connection honest."""
    bucket = _TokenBucket(FLOOD_RATE_PER_SECOND, FLOOD_BURST)
    while True:
        try:
            raw = await _receive_frame(websocket, conn)
        except TimeoutError:
            await _close(websocket, CLOSE_IDLE_TIMEOUT, "idle_timeout")
            return
        except _Kicked:
            return
        except (WebSocketDisconnect, RuntimeError):
            return

        # Flood control: bound frames/sec from this socket before any work.
        if not bucket.allow():
            await _send_ws_error(websocket, "rate_limited", "Slow down", retryable=True)
            continue

        try:
            frame = parse_client_frame(raw)
        except ProtocolError as exc:
            await _send(
                websocket,
                server_frame(
                    "error", {"code": exc.code, "message": exc.message, "retryable": False}
                ),
            )
            continue

        if frame.type == "ping":
            await _send(websocket, server_frame("pong", {"id": frame.id}))
            continue

        if conn.waiting:
            # Queued in the waiting room: re-check the cross-worker decision
            # flag on every frame (idle timeout bounds a silent socket).
            decision = await get_decision(meeting_code, str(user.id))
            if decision == REJECTED:
                # Terminal frame before close (D16), then stop.
                await _send(websocket, server_frame("waiting.rejected", {"user_id": str(user.id)}))
                conn.closed = True
                conn.kick.set()
                await _close(websocket, CLOSE_FORBIDDEN, "rejected")
                return
            if decision != APPROVED:
                if frame.type == "sync":
                    await _send(websocket, server_frame("waiting.state", {"approved": False}))
                else:
                    await _send_ws_error(
                        websocket,
                        "awaiting_approval",
                        "Waiting for the host to admit you",
                    )
                continue
            # Approved: admit, then fall through so a `sync` frame (the
            # client's reaction to waiting.approved) delivers the snapshot.
            await _promote(websocket, meeting_code, meeting, user, conn)

        if frame.type == "sync":
            await _send(websocket, await _snapshot(meeting_code, meeting, str(user.id)))
            last_seq = 0
            if isinstance(frame.payload, dict):
                raw_last_seq = frame.payload.get("last_seq")
                if isinstance(raw_last_seq, int) and raw_last_seq >= 0:
                    last_seq = raw_last_seq
            await _replay_chat(websocket, meeting, last_seq)
        elif frame.type == "presence.update":
            flags = frame.payload if isinstance(frame.payload, dict) else {}
            if flags.get("screen_share_on") is True:
                # Re-read: the host may have flipped the permission after this
                # connection loaded its meeting (same pattern as chat/reactions).
                async with SessionLocal() as session:
                    row = await session.get(Meeting, meeting.id)
                    allowed = row is not None and row.allow_screen_share
                if not allowed:
                    await _send_ws_error(
                        websocket,
                        "permission_denied",
                        "Screen sharing is turned off by the host",
                    )
                    continue
            updated = await presence.update_flags(meeting_code, str(user.id), flags=flags)
            if updated is not None:
                await _broadcast(
                    meeting_code,
                    server_frame(
                        "presence.state",
                        {"participants": await presence.get_presence(meeting_code)},
                    ),
                )
        elif frame.type == "chat.send":
            await _handle_chat_send(websocket, meeting_code, meeting, user, frame)
        elif frame.type == "note.save":
            await _handle_note_save(websocket, meeting_code, meeting, user, frame)
        elif frame.type == "reaction.send":
            await _handle_reaction_send(websocket, meeting_code, meeting, user, frame)
        elif frame.type == "proctor.event":
            await _handle_proctor_event(websocket, meeting_code, meeting, user, frame)
        elif frame.type == "host.action":
            await _handle_host_action(websocket, meeting_code, meeting, user, frame, conn)
        else:
            await _send(
                websocket,
                server_frame(
                    "error",
                    {
                        "code": "unknown_type",
                        "message": f"Unsupported event type: {frame.type}",
                        "retryable": False,
                    },
                ),
            )


async def _close(websocket: WebSocket, code: int, reason: str) -> None:
    with contextlib.suppress(RuntimeError, WebSocketDisconnect):
        await websocket.close(code=code, reason=reason)
