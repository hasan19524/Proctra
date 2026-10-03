"""Application WebSocket gateway (Phases 4-5).

Connect handshake (auth + meeting authorization), versioned envelope loop,
heartbeat/idle handling, Redis pub/sub fan-out, and durable chat (persist to
Postgres first, then broadcast — REALTIME.md §1/§3).
"""

import asyncio
import contextlib
import uuid
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect

from app.core.redis import get_pubsub_client, get_redis
from app.db import SessionLocal
from app.models.meeting import Meeting
from app.models.message import MAX_BODY_LENGTH
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

router = APIRouter()

# The client pings every 25 s (REALTIME.md); no frame for this long = dead peer.
IDLE_TIMEOUT_SECONDS = 60.0
# Upper bound for one reconnect replay (the snapshot also carries a 50-msg tail).
REPLAY_LIMIT = 500


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


async def _broadcast(meeting_code: str, frame_text: str) -> None:
    """Publish a frame to every worker (and thus every connection) in the meeting."""
    try:
        await get_redis().publish(_channel(meeting_code), frame_text)
    except Exception:
        registry = get_registry()
        for conn in registry.in_meeting(meeting_code):
            await _send(conn.websocket, frame_text)


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
            await _send(websocket, data)
    except asyncio.CancelledError:
        raise
    except Exception:
        pass


async def _snapshot(meeting_code: str, meeting: Meeting, user_id: str) -> str:
    """Build the ``sync.state`` full snapshot frame (participants + chat tail)."""
    participants = await presence.get_presence(meeting_code)
    async with SessionLocal() as session:
        recent = await list_recent_messages(session, meeting.id)
    return server_frame(
        "sync.state",
        {
            "meeting": {
                "code": meeting.code,
                "title": meeting.title,
                "status": meeting.status,
                "is_locked": meeting.is_locked,
            },
            "self": {"user_id": user_id},
            "participants": participants,
            "messages": [message_dto(message, sender) for message, sender in recent],
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
        await _serve(websocket, code, meeting, user)
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
            await _broadcast(
                code,
                server_frame("participant.left", {"user_id": str(user.id)}),
            )
        await _broadcast(
            code,
            server_frame("presence.state", {"participants": await presence.get_presence(code)}),
        )


async def _serve(
    websocket: WebSocket,
    meeting_code: str,
    meeting: Meeting,
    user: User,
) -> None:
    """Receive loop: parse envelopes, dispatch, keep the connection honest."""
    while True:
        try:
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=IDLE_TIMEOUT_SECONDS)
        except TimeoutError:
            await _close(websocket, CLOSE_IDLE_TIMEOUT, "idle_timeout")
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
