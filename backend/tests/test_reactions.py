"""Reaction tests (Phase 8): transient fan-out, label whitelist, permission gate."""

from typing import Any

from httpx import AsyncClient

from tests.test_ws import _connect_ready, _create_meeting, _envelope, _register, _ws
from tests.ws_client import WsTestClient


async def _setup_room(client: AsyncClient) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    host = await _register(client, "rhost@procto.dev", "React Host")
    guest = await _register(client, "rguest@procto.dev", "React Guest")
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


class TestReactionSend:
    async def test_reaction_fans_out_with_sender_identity(self, client: AsyncClient) -> None:
        host, guest, meeting = await _setup_room(client)
        ws_host, ws_guest = await _open_pair(meeting, host, guest)

        await ws_guest.send(_envelope("reaction.send", {"label": "Party"}))

        echoed = await ws_guest.receive_type("reaction.received")
        peer = await ws_host.receive_type("reaction.received")

        assert echoed["payload"]["label"] == "Party"
        assert echoed["payload"]["name"] == "React Guest"
        assert echoed["payload"]["user_id"] == guest["user"]["id"]
        assert peer["payload"] == echoed["payload"]
        assert "seq" not in echoed  # transient: no sequence allocated
        await ws_host.close()
        await ws_guest.close()

    async def test_unknown_label_is_rejected_and_socket_stays_usable(
        self, client: AsyncClient
    ) -> None:
        host, _guest, meeting = await _setup_room(client)
        ws = _ws(meeting["code"], host["access_token"])
        await _connect_ready(ws)

        await ws.send(_envelope("reaction.send", {"label": "<img onerror=alert(1)>"}))
        error = await ws.receive_type("error")
        assert error["payload"]["code"] == "invalid_reaction"
        assert error["payload"]["retryable"] is False

        await ws.send(_envelope("reaction.send", {"label": 42}))
        error = await ws.receive_type("error")
        assert error["payload"]["code"] == "invalid_reaction"

        await ws.send(_envelope("ping"))
        assert (await ws.receive_type("pong"))["type"] == "pong"
        await ws.close()

    async def test_permission_gate_follows_allow_reactions(self, client: AsyncClient) -> None:
        host, guest, meeting = await _setup_room(client)
        ws_host, ws_guest = await _open_pair(meeting, host, guest)

        await ws_host.send(
            _envelope("host.action", {"action": "set_permissions", "allow_reactions": False})
        )
        await ws_host.receive_type("permission.changed")

        await ws_guest.send(_envelope("reaction.send", {"label": "Heart"}))
        error = await ws_guest.receive_type("error")
        assert error["payload"]["code"] == "permission_denied"

        await ws_host.send(
            _envelope("host.action", {"action": "set_permissions", "allow_reactions": True})
        )
        await ws_host.receive_type("permission.changed")

        await ws_guest.send(_envelope("reaction.send", {"label": "Heart"}))
        received = await ws_guest.receive_type("reaction.received")
        assert received["payload"]["label"] == "Heart"
        await ws_host.close()
        await ws_guest.close()


class TestHandRaise:
    async def test_hand_raised_flag_round_trips_through_presence(self, client: AsyncClient) -> None:
        host, guest, meeting = await _setup_room(client)
        ws_host, ws_guest = await _open_pair(meeting, host, guest)

        await ws_guest.send(_envelope("presence.update", {"hand_raised": True}))
        seen = False
        for _ in range(5):
            frame = await ws_host.receive_type("presence.state")
            match = next(
                (
                    p
                    for p in frame["payload"]["participants"]
                    if p["user_id"] == guest["user"]["id"]
                ),
                None,
            )
            if match and match.get("hand_raised") is True:
                seen = True
                break
        assert seen, "host never saw the guest's raised hand"

        # Snapshot for a late joiner carries the raised hand too.
        late = await _register(client, "rlate@procto.dev", "Late Guest")
        snapshot = await _connect_ready(_ws(meeting["code"], late["access_token"]))
        match = next(
            (p for p in snapshot["participants"] if p["user_id"] == guest["user"]["id"]), None
        )
        assert match is not None and match.get("hand_raised") is True
        await ws_host.close()
        await ws_guest.close()
