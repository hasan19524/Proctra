"""Screen share presence tests (Phase 10): roster flag + permission gate."""

from typing import Any

from httpx import AsyncClient

from tests.test_ws import _connect_ready, _create_meeting, _envelope, _register, _ws
from tests.ws_client import WsTestClient


async def _setup(client: AsyncClient) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    host = await _register(client, "sshost@procto.dev", "SS Host")
    guest = await _register(client, "ssguest@procto.dev", "SS Guest")
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


def _guest_flag(presence_frame: dict[str, Any], guest_id: str) -> bool | None:
    entry = next(
        (p for p in presence_frame["payload"]["participants"] if p.get("user_id") == guest_id),
        None,
    )
    return None if entry is None else entry.get("screen_share_on")


class TestScreenShareFlag:
    async def test_default_flag_is_off_and_updates_broadcast(self, client: AsyncClient) -> None:
        host, guest, meeting = await _setup(client)
        ws_host, ws_guest = await _open_pair(meeting, host, guest)
        guest_id = guest["user"]["id"]

        await ws_guest.send(_envelope("sync"))
        snapshot = await ws_guest.receive_type("sync.state")
        me = next(p for p in snapshot["payload"]["participants"] if p["user_id"] == guest_id)
        assert me["screen_share_on"] is False

        await ws_guest.send(_envelope("presence.update", {"screen_share_on": True}))
        started = await ws_host.receive_type(
            "presence.state", where=lambda f: _guest_flag(f, guest_id) is True
        )
        assert _guest_flag(started, guest_id) is True
        await ws_guest.receive_type(
            "presence.state", where=lambda f: _guest_flag(f, guest_id) is True
        )

        await ws_guest.send(_envelope("presence.update", {"screen_share_on": False}))
        stopped = await ws_host.receive_type(
            "presence.state", where=lambda f: _guest_flag(f, guest_id) is False
        )
        assert _guest_flag(stopped, guest_id) is False

        await ws_host.close()
        await ws_guest.close()

    async def test_host_permission_gates_the_flag(self, client: AsyncClient) -> None:
        host, guest, meeting = await _setup(client)
        ws_host, ws_guest = await _open_pair(meeting, host, guest)
        guest_id = guest["user"]["id"]

        await ws_host.send(
            _envelope("host.action", {"action": "set_permissions", "allow_screen_share": False})
        )
        for ws in (ws_host, ws_guest):
            changed = await ws.receive_type("permission.changed")
            assert changed["payload"]["allow_screen_share"] is False

        await ws_guest.send(_envelope("presence.update", {"screen_share_on": True}))
        error = await ws_guest.receive_type("error")
        assert error["payload"]["code"] == "permission_denied"
        assert error["payload"]["retryable"] is False

        # The denied flag never landed: snapshots still say off.
        await ws_guest.send(_envelope("sync"))
        snapshot = await ws_guest.receive_type("sync.state")
        assert _guest_flag(snapshot, guest_id) is False

        await ws_host.send(
            _envelope("host.action", {"action": "set_permissions", "allow_screen_share": True})
        )
        for ws in (ws_host, ws_guest):
            await ws.receive_type(
                "permission.changed", where=lambda f: f["payload"]["allow_screen_share"] is True
            )

        await ws_guest.send(_envelope("presence.update", {"screen_share_on": True}))
        allowed = await ws_host.receive_type(
            "presence.state", where=lambda f: _guest_flag(f, guest_id) is True
        )
        assert _guest_flag(allowed, guest_id) is True

        await ws_host.close()
        await ws_guest.close()
