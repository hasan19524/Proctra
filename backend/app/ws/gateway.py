"""Application WebSocket gateway (Phases 4-7).

Connect handshake (auth + meeting authorization), versioned envelope loop,
heartbeat/idle handling, Redis pub/sub fan-out, durable chat (persist to
Postgres first, then broadcast — REALTIME.md §1/§3), host controls, and
shared notes (whole-document saves broadcast as ``note.updated``).
"""

import asyncio
import contextlib
import json
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect

from app.core.redis import get_pubsub_client, get_redis
from app.db import SessionLocal
from app.models.meeting import Meeting
from app.models.message import MAX_BODY_LENGTH
from app.models.note import MAX_NOTE_CONTENT_CHARS, VISIBILITIES, VISIBILITY_HOST_ONLY
from app.models.user import User
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
from app.ws import presence
from app.ws.envelope import (
    CLOSE_FORBIDDEN,
    CLOSE_IDLE_TIMEOUT,
    CLOSE_NOT_FOUND,
    CLOSE_UNAUTHORIZED,
    ProtocolError,
    parse_client_frame,
    server_frame,
)
from app.ws.registry import get_registry
from app.ws.seq import current_seq, next_seq

if TYPE_CHECKING:
    from app.ws.registry import LocalConnection

router = APIRouter()

# The client pings every 25 s (REALTIME.md); no frame for this long = dead peer.
IDLE_TIMEOUT_SECONDS = 60.0
# Upper bound for one reconnect replay (the snapshot also carries a 50-msg tail).
REPLAY_LIMIT = 500


class _Kicked(Exception):
    """The connection was kicked by a host action (remove/end)."""


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


async def _deliver(conn: "LocalConnection", frame_text: str) -> None:
    """Send one broadcast frame to a local connection, honoring visibility."""
    if _is_host_only_note(frame_text) and not conn.is_host:
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
            if _is_host_only_note(data) and not conn.is_host:
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
    current = row or meeting  # re-read so lock/permission changes are visible
    return server_frame(
        "sync.state",
        {
            "meeting": {
                "code": current.code,
                "title": current.title,
                "status": current.status,
                "is_locked": current.is_locked,
                "allow_chat": current.allow_chat,
                "allow_reactions": current.allow_reactions,
                "allow_screen_share": current.allow_screen_share,
            },
            "self": {"user_id": user_id},
            "participants": participants,
            "messages": [message_dto(message, sender) for message, sender in recent],
            "notes": [note_dto(note, name) for note, name in notes],
            "seq": await current_seq(meeting_code),
        },
    )


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
                await session.commit()
            meeting.status = "ended"
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

        await _send_ws_error(websocket, "unknown_action", f"Unsupported host action: {action}")


@router.websocket("/meetings/{meeting_code}")
async def ws_meeting(
    websocket: WebSocket,
    meeting_code: str,
    token: str | None = Query(default=None),
) -> None:
    """Authenticated app-WS endpoint for one meeting (REALTIME.md §1)."""
    code = normalize_code(meeting_code)

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

    # 2. Authorize against the meeting state (Phase 6 adds membership/waiting room).
    if meeting.status == "ended":
        await _reject(websocket, CLOSE_FORBIDDEN, "meeting_ended", "Meeting has ended")
        return
    if meeting.is_locked and not is_host:
        await _reject(websocket, CLOSE_FORBIDDEN, "meeting_locked", "Meeting is locked")
        return

    await websocket.accept()

    registry = get_registry()
    conn = registry.add(code, str(user.id), websocket, is_host=is_host)

    # 3. Presence + fan-out subscription before anything is announced.
    #    Subscribe first: a broadcast published before the subscription is
    #    active would be silently lost.
    pubsub = get_pubsub_client().pubsub()
    await pubsub.subscribe(_channel(code))
    listener = asyncio.create_task(_relay(websocket, code, conn.conn_id, pubsub))
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

    # 4. Handshake snapshot, then announce the join to everyone.
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


async def _serve(
    websocket: WebSocket,
    meeting_code: str,
    meeting: Meeting,
    user: User,
    conn: "LocalConnection",
) -> None:
    """Receive loop: parse envelopes, dispatch, keep the connection honest."""
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
        elif frame.type == "sync":
            await _send(websocket, await _snapshot(meeting_code, meeting, str(user.id)))
            last_seq = 0
            if isinstance(frame.payload, dict):
                raw_last_seq = frame.payload.get("last_seq")
                if isinstance(raw_last_seq, int) and raw_last_seq >= 0:
                    last_seq = raw_last_seq
            await _replay_chat(websocket, meeting, last_seq)
        elif frame.type == "presence.update":
            updated = await presence.update_flags(meeting_code, str(user.id), flags=frame.payload)
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
