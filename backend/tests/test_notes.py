"""Notes tests (Phase 7): persistence, fan-out, visibility filtering, validation."""

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db import SessionLocal
from app.models.note import MeetingNote
from tests.test_ws import _connect_ready, _create_meeting, _envelope, _register, _ws
from tests.ws_client import WsTestClient


async def _setup_room(client: AsyncClient) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    host = await _register(client, "nhost@procto.dev", "Note Host")
    guest = await _register(client, "nguest@procto.dev", "Note Guest")
    meeting = await _create_meeting(client, host["access_token"])
    return host, guest, meeting


async def _open_pair(
    meeting: dict[str, Any], host: dict[str, Any], guest: dict[str, Any]
) -> tuple[WsTestClient, WsTestClient]:
    ws_host = _ws(meeting["code"], host["access_token"])
    await _connect_ready(ws_host)
    ws_guest = _ws(meeting["code"], guest["access_token"])
    await _connect_ready(ws_guest)
    await ws_host.receive_type("participant.joined")
    await ws_host.receive_type("presence.state")
    return ws_host, ws_guest


async def _note_rows() -> list[MeetingNote]:
    async with SessionLocal() as session:
        result = await session.scalars(select(MeetingNote))
        return list(result.all())


class TestNoteSave:
    async def test_save_persists_and_fans_out(self, client: AsyncClient) -> None:
        host, guest, meeting = await _setup_room(client)
        ws_host, ws_guest = await _open_pair(meeting, host, guest)

        content = {"text": "Agenda\n1. Intro"}
        await ws_host.send(_envelope("note.save", {"visibility": "all", "content": content}))

        echoed = await ws_host.receive_type("note.updated")
        peer = await ws_guest.receive_type("note.updated")

        assert echoed["payload"]["content"] == content
        assert echoed["payload"]["visibility"] == "all"
        assert echoed["payload"]["updated_by_name"] == "Note Host"
        assert peer["payload"]["id"] == echoed["payload"]["id"]

        rows = await _note_rows()
        assert len(rows) == 1
        assert rows[0].content == content
        assert rows[0].visibility == "all"
        await ws_host.close()
        await ws_guest.close()

    async def test_second_save_replaces_the_same_document(self, client: AsyncClient) -> None:
        host, _guest, meeting = await _setup_room(client)
        ws = _ws(meeting["code"], host["access_token"])
        await _connect_ready(ws)

        await ws.send(_envelope("note.save", {"content": {"text": "v1"}}))
        first = await ws.receive_type("note.updated")
        await ws.send(_envelope("note.save", {"content": {"text": "v2"}}))
        second = await ws.receive_type("note.updated")

        assert first["payload"]["id"] == second["payload"]["id"]
        assert second["payload"]["content"] == {"text": "v2"}
        rows = await _note_rows()
        assert len(rows) == 1
        assert rows[0].content == {"text": "v2"}
        await ws.close()

    async def test_invalid_visibility_and_content_are_rejected(self, client: AsyncClient) -> None:
        host, _guest, meeting = await _setup_room(client)
        ws = _ws(meeting["code"], host["access_token"])
        await _connect_ready(ws)

        await ws.send(_envelope("note.save", {"visibility": "secret", "content": {}}))
        error = await ws.receive_type("error")
        assert error["payload"]["code"] == "invalid_note"

        await ws.send(_envelope("note.save", {"content": "not-an-object"}))
        error = await ws.receive_type("error")
        assert error["payload"]["code"] == "invalid_note"

        await ws.send(_envelope("note.save", {"content": {"text": "x" * 100_001}}))
        error = await ws.receive_type("error")
        assert error["payload"]["code"] == "invalid_note"

        # The socket stays usable after validation errors.
        await ws.send(_envelope("ping"))
        assert (await ws.receive_type("pong"))["type"] == "pong"
        assert await _note_rows() == []
        await ws.close()


class TestHostOnlyVisibility:
    async def test_host_saves_host_only_note_and_guest_never_sees_it(
        self, client: AsyncClient
    ) -> None:
        host, guest, meeting = await _setup_room(client)
        ws_host, ws_guest = await _open_pair(meeting, host, guest)

        await ws_host.send(
            _envelope("note.save", {"visibility": "host_only", "content": {"text": "private"}})
        )
        echo = await ws_host.receive_type("note.updated")
        assert echo["payload"]["visibility"] == "host_only"

        # The host socket got the broadcast; the guest's copy is suppressed.
        with pytest.raises(TimeoutError):
            await ws_guest.receive_type("note.updated", timeout=1.0)

        # Snapshots: host sees both documents, guest only the shared one.
        await ws_host.send(
            _envelope("note.save", {"visibility": "all", "content": {"text": "pub"}})
        )
        await ws_host.receive_type("note.updated")

        host_snap = await _connect_ready(_ws(meeting["code"], host["access_token"]))
        guest_snap = await _connect_ready(_ws(meeting["code"], guest["access_token"]))
        assert {n["visibility"] for n in host_snap["notes"]} == {"all", "host_only"}
        assert {n["visibility"] for n in guest_snap["notes"]} == {"all"}
        await ws_host.close()
        await ws_guest.close()

    async def test_guest_cannot_save_host_only_note(self, client: AsyncClient) -> None:
        host, guest, meeting = await _setup_room(client)
        ws_host, ws_guest = await _open_pair(meeting, host, guest)

        await ws_guest.send(
            _envelope("note.save", {"visibility": "host_only", "content": {"text": "sneaky"}})
        )
        error = await ws_guest.receive_type("error")
        assert error["payload"]["code"] == "permission_denied"
        assert await _note_rows() == []
        await ws_host.close()
        await ws_guest.close()


class TestNoteSnapshot:
    async def test_late_joiner_receives_persisted_notes(self, client: AsyncClient) -> None:
        host, _guest, meeting = await _setup_room(client)
        ws_host = _ws(meeting["code"], host["access_token"])
        await _connect_ready(ws_host)
        await ws_host.send(_envelope("note.save", {"content": {"text": "decisions from standup"}}))
        await ws_host.receive_type("note.updated")

        guest = await _register(client, "nlate@procto.dev", "Late Guest")
        snapshot = await _connect_ready(_ws(meeting["code"], guest["access_token"]))

        assert len(snapshot["notes"]) == 1
        assert snapshot["notes"][0]["content"] == {"text": "decisions from standup"}
        assert snapshot["notes"][0]["updated_by_name"] == "Note Host"
        await ws_host.close()

    async def test_empty_notes_snapshot(self, client: AsyncClient) -> None:
        host, _guest, meeting = await _setup_room(client)
        snapshot = await _connect_ready(_ws(meeting["code"], host["access_token"]))
        assert snapshot["notes"] == []
