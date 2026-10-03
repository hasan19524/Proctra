"""Host control tests (Phase 6): lock/end, mute/remove, permissions, attendance."""

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db import SessionLocal
from app.models.meeting import Meeting
from app.models.participant import MeetingParticipant
from app.ws.envelope import CLOSE_FORBIDDEN
from tests.test_ws import (
    _connect_ready,
    _create_meeting,
    _envelope,
    _expect_reject,
    _register,
    _ws,
)
from tests.ws_client import WsDisconnect, WsTestClient


async def _setup(client: AsyncClient) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    host = await _register(client, "hhost@procto.dev", "Host Person")
    guest = await _register(client, "hguest@procto.dev", "Guest Person")
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


class TestAuthorization:
    async def test_non_host_action_is_forbidden(self, client: AsyncClient) -> None:
        host, guest, meeting = await _setup(client)
        _ws_host, ws_guest = await _open_pair(meeting, host, guest)

        await ws_guest.send(_envelope("host.action", {"action": "lock"}))
        error = await ws_guest.receive_type("error")
        assert error["payload"]["code"] == "forbidden"
        assert error["payload"]["retryable"] is False

        async with SessionLocal() as session:
            row = await session.get(Meeting, meeting["id"])
            assert row is not None
            assert row.is_locked is False

    async def test_unknown_action_is_rejected(self, client: AsyncClient) -> None:
        host, _guest, meeting = await _setup(client)
        ws = _ws(meeting["code"], host["access_token"])
        await _connect_ready(ws)
        await ws.send(_envelope("host.action", {"action": "teleport"}))
        error = await ws.receive_type("error")
        assert error["payload"]["code"] == "unknown_action"
        await ws.close()


class TestLockAndEnd:
    async def test_lock_broadcasts_and_blocks_new_guests(self, client: AsyncClient) -> None:
        host, guest, meeting = await _setup(client)
        ws_host, ws_guest = await _open_pair(meeting, host, guest)

        await ws_host.send(_envelope("host.action", {"action": "lock"}))
        for ws in (ws_host, ws_guest):
            locked = await ws.receive_type("meeting.locked")
            assert locked["payload"]["is_locked"] is True

        # A new guest is rejected while locked...
        late = await _register(client, "hlate@procto.dev", "Late Guest")
        await _expect_reject(
            _ws(meeting["code"], late["access_token"]), CLOSE_FORBIDDEN, "meeting_locked"
        )
        # ...and the host can still get back in.
        ws_again = _ws(meeting["code"], host["access_token"])
        await _connect_ready(ws_again)
        await ws_again.close()

        await ws_host.close()
        await ws_guest.close()

    async def test_end_closes_everyone_and_persists(self, client: AsyncClient) -> None:
        host, guest, meeting = await _setup(client)
        ws_host, ws_guest = await _open_pair(meeting, host, guest)

        await ws_host.send(_envelope("host.action", {"action": "end"}))

        ended = await ws_guest.receive_type("meeting.ended")
        assert ended["type"] == "meeting.ended"
        with pytest.raises(WsDisconnect) as exc_info:
            await ws_guest.receive()
        assert exc_info.value.code == CLOSE_FORBIDDEN

        await ws_host.receive_type("meeting.ended")
        with pytest.raises(WsDisconnect) as host_exc:
            await ws_host.receive()
        assert host_exc.value.code == CLOSE_FORBIDDEN

        async with SessionLocal() as session:
            row = await session.get(Meeting, meeting["id"])
            assert row is not None
            assert row.status == "ended"
            assert row.ended_at is not None

        late = await _register(client, "hlate2@procto.dev", "Late Guest")
        await _expect_reject(
            _ws(meeting["code"], late["access_token"]), CLOSE_FORBIDDEN, "meeting_ended"
        )


class TestMuteAndRemove:
    async def test_mute_participant_broadcasts_to_the_room(self, client: AsyncClient) -> None:
        host, guest, meeting = await _setup(client)
        ws_host, ws_guest = await _open_pair(meeting, host, guest)
        guest_id = guest["user"]["id"]

        await ws_host.send(
            _envelope("host.action", {"action": "mute_participant", "target_id": guest_id})
        )
        for ws in (ws_host, ws_guest):
            muted = await ws.receive_type("participant.muted")
            assert muted["payload"]["user_id"] == guest_id
            assert muted["payload"]["by_user_id"] == host["user"]["id"]

        await ws_host.send(
            _envelope("host.action", {"action": "mute_participant", "target_id": "nobody"})
        )
        error = await ws_host.receive_type("error")
        assert error["payload"]["code"] == "invalid_target"

        await ws_host.close()
        await ws_guest.close()

    async def test_remove_disconnects_the_target(self, client: AsyncClient) -> None:
        host, guest, meeting = await _setup(client)
        ws_host, ws_guest = await _open_pair(meeting, host, guest)
        guest_id = guest["user"]["id"]

        await ws_host.send(_envelope("host.action", {"action": "remove", "target_id": guest_id}))

        removed = await ws_guest.receive_type("participant.removed")
        assert removed["payload"]["user_id"] == guest_id
        with pytest.raises(WsDisconnect) as exc_info:
            await ws_guest.receive()
        assert exc_info.value.code == CLOSE_FORBIDDEN

        # The host sees the guest leave the roster.
        left = await ws_host.receive_type("participant.left")
        assert left["payload"]["user_id"] == guest_id
        presence = await ws_host.receive_type("presence.state")
        assert guest_id not in {p.get("user_id") for p in presence["payload"]["participants"]}

        # Removing yourself is rejected.
        await ws_host.send(
            _envelope("host.action", {"action": "remove", "target_id": host["user"]["id"]})
        )
        error = await ws_host.receive_type("error")
        assert error["payload"]["code"] == "invalid_target"
        await ws_host.close()


class TestPermissions:
    async def test_disabling_chat_blocks_sends_until_reenabled(self, client: AsyncClient) -> None:
        host, guest, meeting = await _setup(client)
        ws_host, ws_guest = await _open_pair(meeting, host, guest)

        await ws_host.send(
            _envelope("host.action", {"action": "set_permissions", "allow_chat": False})
        )
        for ws in (ws_host, ws_guest):
            changed = await ws.receive_type("permission.changed")
            assert changed["payload"]["allow_chat"] is False
            assert changed["payload"]["allow_reactions"] is True

        await ws_guest.send(_envelope("chat.send", {"body": "should be blocked"}))
        error = await ws_guest.receive_type("error")
        assert error["payload"]["code"] == "permission_denied"

        await ws_host.send(
            _envelope("host.action", {"action": "set_permissions", "allow_chat": True})
        )
        await ws_host.receive_type("permission.changed")
        await ws_guest.receive_type("permission.changed")

        await ws_guest.send(_envelope("chat.send", {"body": "allowed again"}))
        delivered = await ws_guest.receive_type("chat.message")
        assert delivered["payload"]["body"] == "allowed again"

        # Snapshots carry the current flags.
        await ws_guest.send(_envelope("sync"))
        snapshot = await ws_guest.receive_type("sync.state")
        assert snapshot["payload"]["meeting"]["allow_chat"] is True

        await ws_host.close()
        await ws_guest.close()


class TestAttendance:
    async def test_join_and_leave_rows_are_recorded(self, client: AsyncClient) -> None:
        host, guest, meeting = await _setup(client)
        ws_host, ws_guest = await _open_pair(meeting, host, guest)

        async def _rows() -> list[MeetingParticipant]:
            async with SessionLocal() as session:
                result = await session.scalars(
                    select(MeetingParticipant).order_by(MeetingParticipant.joined_at)
                )
                return list(result.all())

        rows = await _rows()
        assert len(rows) == 2
        by_role = {row.role for row in rows}
        assert by_role == {"host", "participant"}
        assert all(row.left_at is None for row in rows)

        await ws_guest.close()
        rows = await _rows()
        guest_rows = [r for r in rows if r.role == "participant"]
        host_rows = [r for r in rows if r.role == "host"]
        assert len(guest_rows) == 1 and guest_rows[0].left_at is not None
        assert len(host_rows) == 1 and host_rows[0].left_at is None

        await ws_host.close()
        rows = await _rows()
        assert all(row.left_at is not None for row in rows)
