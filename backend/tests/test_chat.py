"""Chat tests (Phase 5): persistence, fan-out, snapshot tail, replay, idempotency."""

from typing import Any

from httpx import AsyncClient
from sqlalchemy import select

from app.db import SessionLocal
from app.models.message import Message
from tests.test_ws import _connect_ready, _create_meeting, _envelope, _register, _ws
from tests.ws_client import WsTestClient


async def _setup_room(client: AsyncClient) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Register a host + guest and create a meeting; returns (host, guest, meeting)."""
    host = await _register(client, "chost@procto.dev", "Host Person")
    guest = await _register(client, "cguest@procto.dev", "Guest Person")
    meeting = await _create_meeting(client, host["access_token"])
    return host, guest, meeting


async def _open_pair(
    meeting: dict[str, Any], host: dict[str, Any], guest: dict[str, Any]
) -> tuple[WsTestClient, WsTestClient]:
    """Two ready sockets; drains the join frames on both sides."""
    ws_host = _ws(meeting["code"], host["access_token"])
    await _connect_ready(ws_host)
    ws_guest = _ws(meeting["code"], guest["access_token"])
    await _connect_ready(ws_guest)
    await ws_host.receive_type("participant.joined")
    await ws_host.receive_type("presence.state")
    return ws_host, ws_guest


async def _message_rows() -> list[Message]:
    async with SessionLocal() as session:
        result = await session.scalars(select(Message).order_by(Message.seq))
        return list(result.all())


class TestChatSend:
    async def test_chat_send_persists_and_fans_out(self, client: AsyncClient) -> None:
        host, guest, meeting = await _setup_room(client)
        ws_host, ws_guest = await _open_pair(meeting, host, guest)

        await ws_host.send(_envelope("chat.send", {"body": "hello procto", "client_id": "c-1"}))

        sent = await ws_host.receive_type("chat.message")
        echoed = await ws_guest.receive_type("chat.message")

        payload = sent["payload"]
        assert payload["body"] == "hello procto"
        assert payload["sender_name"] == "Host Person"
        assert payload["client_id"] == "c-1"
        assert sent["seq"] == 1
        assert echoed["payload"]["id"] == payload["id"]
        assert echoed["seq"] == 1

        rows = await _message_rows()
        assert len(rows) == 1
        assert rows[0].body == "hello procto"
        assert rows[0].seq == 1
        await ws_host.close()
        await ws_guest.close()

    async def test_blank_and_oversized_bodies_are_rejected(self, client: AsyncClient) -> None:
        host, _guest, meeting = await _setup_room(client)
        ws = _ws(meeting["code"], host["access_token"])
        await _connect_ready(ws)

        await ws.send(_envelope("chat.send", {"body": "   "}))
        error = await ws.receive_type("error")
        assert error["payload"]["code"] == "invalid_message"
        assert error["payload"]["retryable"] is False

        await ws.send(_envelope("chat.send", {"body": "x" * 4001}))
        error = await ws.receive_type("error")
        assert error["payload"]["code"] == "invalid_message"

        # The socket stays usable after validation errors.
        await ws.send(_envelope("ping"))
        assert (await ws.receive_type("pong"))["type"] == "pong"
        assert await _message_rows() == []
        await ws.close()

    async def test_same_client_id_does_not_duplicate(self, client: AsyncClient) -> None:
        host, _guest, meeting = await _setup_room(client)
        ws = _ws(meeting["code"], host["access_token"])
        await _connect_ready(ws)

        await ws.send(_envelope("chat.send", {"body": "retry me", "client_id": "dup-1"}))
        first = await ws.receive_type("chat.message")
        await ws.send(_envelope("chat.send", {"body": "retry me", "client_id": "dup-1"}))
        second = await ws.receive_type("chat.message")

        # At-least-once: both attempts broadcast, but Postgres keeps one row.
        assert first["payload"]["id"] == second["payload"]["id"]
        rows = await _message_rows()
        assert len(rows) == 1
        await ws.close()


class TestChatSnapshotAndReplay:
    async def test_snapshot_carries_chat_tail(self, client: AsyncClient) -> None:
        host, guest, meeting = await _setup_room(client)
        ws_host = _ws(meeting["code"], host["access_token"])
        await _connect_ready(ws_host)
        await ws_host.send(_envelope("chat.send", {"body": "earlier message"}))
        await ws_host.receive_type("chat.message")

        ws_guest = _ws(meeting["code"], guest["access_token"])
        payload = await _connect_ready(ws_guest)

        assert len(payload["messages"]) == 1
        assert payload["messages"][0]["body"] == "earlier message"
        assert payload["messages"][0]["sender_name"] == "Host Person"
        await ws_host.close()
        await ws_guest.close()

    async def test_reconnect_replays_only_missed_messages(self, client: AsyncClient) -> None:
        host, guest, meeting = await _setup_room(client)
        ws_host, ws_guest = await _open_pair(meeting, host, guest)

        await ws_host.send(_envelope("chat.send", {"body": "msg one", "client_id": "m1"}))
        first = await ws_host.receive_type("chat.message")
        await ws_guest.receive_type("chat.message")
        assert first["seq"] == 1

        # Guest drops offline.
        await ws_guest.close()
        await ws_host.send(_envelope("chat.send", {"body": "msg two", "client_id": "m2"}))
        await ws_host.receive_type("chat.message")

        # Guest reconnects and asks for everything after seq 1.
        ws_again = _ws(meeting["code"], guest["access_token"])
        await _connect_ready(ws_again)
        await ws_again.send(_envelope("sync", {"last_seq": 1}))
        await ws_again.receive_type("sync.state")
        replayed = await ws_again.receive_type("chat.message")
        assert replayed["seq"] == 2
        assert replayed["payload"]["body"] == "msg two"

        # Nothing else is pending — msg one was not re-sent.
        await ws_again.send(_envelope("ping"))
        assert (await ws_again.receive_type("pong"))["type"] == "pong"

        await ws_host.close()
        await ws_again.close()
