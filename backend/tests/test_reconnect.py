"""Failure + reconnection tests (Phase 12): idle timeout, drop and rejoin."""

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db import SessionLocal
from app.models.participant import MeetingParticipant
from app.ws import gateway
from app.ws.envelope import CLOSE_IDLE_TIMEOUT
from tests.test_ws import _connect_ready, _create_meeting, _envelope, _register, _ws
from tests.ws_client import WsDisconnect


async def _setup(client: AsyncClient, email: str, name: str) -> dict[str, Any]:
    user = await _register(client, email, name)
    meeting = await _create_meeting(client, user["access_token"])
    return {"user": user, "meeting": meeting}


class TestIdleTimeout:
    async def test_idle_socket_is_closed_with_4013_and_can_rejoin(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        setup = await _setup(client, "idle@procto.dev", "Idle Iris")
        user, meeting = setup["user"], setup["meeting"]
        monkeypatch.setattr(gateway, "IDLE_TIMEOUT_SECONDS", 0.2)

        ws = _ws(meeting["code"], user["access_token"])
        await _connect_ready(ws)
        with pytest.raises(WsDisconnect) as exc:
            await ws.receive(timeout=5.0)
        assert exc.value.code == CLOSE_IDLE_TIMEOUT

        # The timeout is not a ban: the same user reconnects immediately.
        monkeypatch.setattr(gateway, "IDLE_TIMEOUT_SECONDS", 60.0)
        again = _ws(meeting["code"], user["access_token"])
        await _connect_ready(again)
        await again.close()


class TestDropAndRejoin:
    async def test_drop_releases_presence_and_rejoin_restores_state(
        self, client: AsyncClient
    ) -> None:
        host_setup = await _setup(client, "drop-host@procto.dev", "Drop Host")
        guest = await _register(client, "drop-guest@procto.dev", "Drop Guest")
        host, meeting = host_setup["user"], host_setup["meeting"]

        ws_host = _ws(meeting["code"], host["access_token"])
        await _connect_ready(ws_host)
        ws_guest = _ws(meeting["code"], guest["access_token"])
        await _connect_ready(ws_guest)
        await ws_host.receive_type("participant.joined")
        await ws_host.receive_type("presence.state")
        guest_id = guest["user"]["id"]

        # A durable message before the drop must be waiting after the rejoin.
        await ws_guest.send(
            _envelope("chat.send", {"body": "before the drop", "client_id": "drop-1"})
        )
        await ws_guest.receive_type("chat.message")
        await ws_host.receive_type("chat.message")

        await ws_guest.close()

        # The host watches the guest disappear from presence.
        left = await ws_host.receive_type("participant.left")
        assert left["payload"]["user_id"] == guest_id
        presence = await ws_host.receive_type("presence.state")
        assert guest_id not in {p["user_id"] for p in presence["payload"]["participants"]}

        # Rejoin: a fresh socket gets the snapshot, tail including the message...
        ws_again = _ws(meeting["code"], guest["access_token"])
        sync_payload = await _connect_ready(ws_again)
        tail = sync_payload.get("messages") or []
        assert any(m["body"] == "before the drop" for m in tail), [m["body"] for m in tail]

        # ...and the host sees the guest return.
        rejoined = await ws_host.receive_type("participant.joined")
        assert rejoined["payload"]["user_id"] == guest_id
        await ws_host.receive_type("presence.state")

        # Attendance recorded two sessions: the first one closed, second open.
        async with SessionLocal() as session:
            rows = list(
                (
                    await session.scalars(
                        select(MeetingParticipant)
                        .where(MeetingParticipant.user_id == uuid.UUID(guest_id))
                        .order_by(MeetingParticipant.joined_at)
                    )
                ).all()
            )
        assert len(rows) == 2
        assert rows[0].left_at is not None
        assert rows[1].left_at is None

        await ws_host.close()
        await ws_again.close()
