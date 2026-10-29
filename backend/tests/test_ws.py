"""WebSocket gateway tests (Phase 4): handshake auth, envelope, presence fan-out."""

import json
from typing import Any, cast

import pytest
from httpx import AsyncClient

from app.db import SessionLocal
from app.main import app as fastapi_app
from app.models.meeting import Meeting
from app.ws.envelope import (
    CLOSE_FORBIDDEN,
    CLOSE_NOT_FOUND,
    CLOSE_UNAUTHORIZED,
    ProtocolError,
    parse_client_frame,
    server_frame,
)
from tests.ws_client import WsDisconnect, WsTestClient

WS_PATH = "/api/v1/ws/meetings"


def _envelope(frame_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"v": 1, "type": frame_type, "payload": payload or {}}


async def _register(client: AsyncClient, email: str, name: str) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-1", "display_name": name},
    )
    assert response.status_code == 201, response.text
    data: dict[str, Any] = response.json()
    return data


async def _create_meeting(client: AsyncClient, token: str) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/meetings",
        json={"title": "WS room"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201, response.text
    data: dict[str, Any] = response.json()
    return data


def _ws(
    code: str,
    token: str | None = None,
    password: str | None = None,
    *,
    echo_subprotocol: bool = True,
) -> WsTestClient:
    """Connect to a meeting WS. Credentials ride Sec-WebSocket-Protocol (H1)."""
    return WsTestClient(
        fastapi_app,
        f"{WS_PATH}/{code}",
        token=token,
        password=password,
        echo_subprotocol=echo_subprotocol,
    )


async def _connect_ready(ws: WsTestClient) -> dict[str, Any]:
    """Connect and drain the self-join frames; returns the sync.state payload."""
    await ws.connect()
    sync = await ws.receive_type("sync.state")
    await ws.receive_type("participant.joined")
    await ws.receive_type("presence.state")
    payload: dict[str, Any] = sync["payload"]
    return payload


async def _expect_reject(ws: WsTestClient, close_code: int, err_code: str) -> None:
    """Connect (accept-then-close), assert the error frame and close code."""
    await ws.connect()
    error = await ws.receive()
    assert error["type"] == "error"
    assert error["payload"]["code"] == err_code
    assert error["payload"]["retryable"] is False
    with pytest.raises(WsDisconnect) as exc_info:
        await ws.receive()
    assert exc_info.value.code == close_code


class TestEnvelope:
    async def test_parses_a_valid_frame(self) -> None:
        frame = parse_client_frame('{"v":1,"type":"ping","payload":{}}')
        assert frame.type == "ping"
        assert frame.payload == {}

    async def test_rejects_bad_json(self) -> None:
        with pytest.raises(ProtocolError) as exc_info:
            parse_client_frame("not json")
        assert exc_info.value.code == "bad_json"

    async def test_rejects_wrong_version(self) -> None:
        with pytest.raises(ProtocolError) as exc_info:
            parse_client_frame('{"v":99,"type":"ping"}')
        assert exc_info.value.code == "bad_version"

    async def test_server_frame_shape(self) -> None:
        data = json.loads(server_frame("pong", {"x": 1}, seq=7))
        assert data["v"] == 1
        assert data["type"] == "pong"
        assert data["seq"] == 7
        assert data["id"]
        assert data["ts"].endswith("Z")


class TestHandshake:
    async def test_missing_token_is_rejected_with_4001(self, client: AsyncClient) -> None:
        await _expect_reject(_ws("abc-def-ghi"), CLOSE_UNAUTHORIZED, "unauthorized")

    async def test_invalid_token_is_4001(self, client: AsyncClient) -> None:
        await _expect_reject(_ws("abc-def-ghi", "not-a-jwt"), CLOSE_UNAUTHORIZED, "unauthorized")

    async def test_unknown_meeting_is_4004(self, client: AsyncClient) -> None:
        auth = await _register(client, "host4004@procto.dev", "Host")
        await _expect_reject(_ws("zzz-zzz-zzz", auth["access_token"]), CLOSE_NOT_FOUND, "not_found")

    async def test_ended_meeting_is_4003(self, client: AsyncClient) -> None:
        auth = await _register(client, "hostended@procto.dev", "Host")
        meeting = await _create_meeting(client, auth["access_token"])

        async with SessionLocal() as session:
            row = await session.get(Meeting, meeting["id"])
            assert row is not None
            row.status = "ended"
            await session.commit()

        await _expect_reject(
            _ws(meeting["code"], auth["access_token"]), CLOSE_FORBIDDEN, "meeting_ended"
        )

    async def test_locked_meeting_blocks_guests_but_not_host(self, client: AsyncClient) -> None:
        host = await _register(client, "lockhost@procto.dev", "Host")
        guest = await _register(client, "lockguest@procto.dev", "Guest")
        meeting = await _create_meeting(client, host["access_token"])

        async with SessionLocal() as session:
            row = await session.get(Meeting, meeting["id"])
            assert row is not None
            row.is_locked = True
            await session.commit()

        await _expect_reject(
            _ws(meeting["code"], guest["access_token"]), CLOSE_FORBIDDEN, "meeting_locked"
        )

        host_ws = _ws(meeting["code"], host["access_token"])
        payload = await _connect_ready(host_ws)
        assert payload["meeting"]["code"] == meeting["code"]
        assert payload["meeting"]["is_locked"] is True
        await host_ws.close()


class TestCredentialTransport:
    """H1 regression: join secrets ride Sec-WebSocket-Protocol, never the URL."""

    async def test_token_in_query_string_is_rejected(self, client: AsyncClient) -> None:
        # A legacy-style client that puts the token in ?token= must not get in:
        # the gateway no longer reads credentials from the query string.
        auth = await _register(client, "h1query@procto.dev", "Host")
        meeting = await _create_meeting(client, auth["access_token"])
        legacy = WsTestClient(
            fastapi_app,
            f"{WS_PATH}/{meeting['code']}",
            query={"token": auth["access_token"]},
        )
        await _expect_reject(legacy, CLOSE_UNAUTHORIZED, "unauthorized")

    async def test_valid_token_in_subprotocol_connects(self, client: AsyncClient) -> None:
        auth = await _register(client, "h1header@procto.dev", "Host")
        meeting = await _create_meeting(client, auth["access_token"])

        ws = _ws(meeting["code"], auth["access_token"])
        payload = await _connect_ready(ws)
        assert payload["meeting"]["code"] == meeting["code"]
        assert ws.accepted_subprotocol == "procto.v1"
        await ws.close()

    async def test_malformed_base64_token_is_rejected(self, client: AsyncClient) -> None:
        ws = WsTestClient(
            fastapi_app,
            f"{WS_PATH}/abc-def-ghi",
            echo_subprotocol=False,
        )
        ws._scope["subprotocols"] = ["procto.v1", "procto.token.%%%not-base64%%%"]
        ws._scope["headers"].append(
            (b"sec-websocket-protocol", b"procto.v1, procto.token.%%%not-base64%%%")
        )
        await _expect_reject(ws, CLOSE_UNAUTHORIZED, "unauthorized")

    async def test_password_round_trips_via_subprotocol(self, client: AsyncClient) -> None:
        host = await _register(client, "h1pw@procto.dev", "Host")
        guest = await _register(client, "h1pwguest@procto.dev", "Guest")
        created = await client.post(
            "/api/v1/meetings",
            json={"title": "Locked exam", "password": "sesame12", "waiting_room": False},
            headers={"Authorization": f"Bearer {host['access_token']}"},
        )
        assert created.status_code == 201, created.text
        meeting = cast(dict[str, Any], created.json())

        # Wrong password still lands on the guarded path, not a crash.
        bad = _ws(meeting["code"], guest["access_token"], "wrong-pass")
        await _expect_reject(bad, CLOSE_FORBIDDEN, "wrong_password")

        # Correct password connects — proving the header value reached verify_password.
        good = _ws(meeting["code"], guest["access_token"], "sesame12")
        payload = await _connect_ready(good)
        assert payload["meeting"]["code"] == meeting["code"]
        await good.close()


class TestSession:
    async def test_sync_state_snapshot_contains_self_and_meeting(self, client: AsyncClient) -> None:
        auth = await _register(client, "snap@procto.dev", "Hasan")
        meeting = await _create_meeting(client, auth["access_token"])

        ws = _ws(meeting["code"], auth["access_token"])
        await ws.connect()
        payload = (await ws.receive_type("sync.state"))["payload"]

        assert payload["meeting"]["code"] == meeting["code"]
        assert payload["meeting"]["status"] == "waiting"
        assert payload["self"]["user_id"] == auth["user"]["id"]
        assert payload["seq"] == 0
        assert [p["name"] for p in payload["participants"]] == ["Hasan"]
        assert payload["participants"][0]["is_host"] is True

        await ws.close()

    async def test_ping_gets_pong(self, client: AsyncClient) -> None:
        auth = await _register(client, "ping@procto.dev", "Pinger")
        meeting = await _create_meeting(client, auth["access_token"])

        ws = _ws(meeting["code"], auth["access_token"])
        await _connect_ready(ws)

        await ws.send({"v": 1, "type": "ping", "id": "c1", "payload": {}})
        pong = await ws.receive_type("pong")
        assert pong["payload"]["id"] == "c1"

        await ws.close()

    async def test_unknown_event_type_returns_error_frame(self, client: AsyncClient) -> None:
        auth = await _register(client, "unknown@procto.dev", "U")
        meeting = await _create_meeting(client, auth["access_token"])

        ws = _ws(meeting["code"], auth["access_token"])
        await _connect_ready(ws)

        await ws.send(_envelope("totally.unknown"))
        error = await ws.receive_type("error")
        assert error["payload"]["code"] == "unknown_type"
        assert error["payload"]["retryable"] is False

        await ws.close()

    async def test_malformed_frame_returns_bad_json(self, client: AsyncClient) -> None:
        auth = await _register(client, "malformed@procto.dev", "M")
        meeting = await _create_meeting(client, auth["access_token"])

        ws = _ws(meeting["code"], auth["access_token"])
        await _connect_ready(ws)

        await ws.send("this is not json")
        error = await ws.receive_type("error")
        assert error["payload"]["code"] == "bad_json"

        await ws.close()

    async def test_sync_request_resends_snapshot(self, client: AsyncClient) -> None:
        auth = await _register(client, "resync@procto.dev", "Re")
        meeting = await _create_meeting(client, auth["access_token"])

        ws = _ws(meeting["code"], auth["access_token"])
        await _connect_ready(ws)

        await ws.send(_envelope("sync", {"last_seq": 0}))
        second = await ws.receive_type("sync.state")
        assert second["payload"]["self"]["user_id"] == auth["user"]["id"]

        await ws.close()


class TestPresenceFanout:
    async def test_second_client_sees_both_participants(self, client: AsyncClient) -> None:
        host = await _register(client, "fanhost@procto.dev", "Host")
        guest = await _register(client, "fanguest@procto.dev", "Guest")
        meeting = await _create_meeting(client, host["access_token"])

        host_ws = _ws(meeting["code"], host["access_token"])
        await _connect_ready(host_ws)

        guest_ws = _ws(meeting["code"], guest["access_token"])
        guest_sync = await _connect_ready(guest_ws)
        assert [p["name"] for p in guest_sync["participants"]] == ["Host", "Guest"]

        joined = await host_ws.receive_type("participant.joined")
        assert joined["payload"]["name"] == "Guest"
        presence = await host_ws.receive_type("presence.state")
        assert len(presence["payload"]["participants"]) == 2

        await guest_ws.close()
        await host_ws.close()

    async def test_presence_update_broadcasts_flags(self, client: AsyncClient) -> None:
        host = await _register(client, "flaghost@procto.dev", "Host")
        guest = await _register(client, "flagguest@procto.dev", "Guest")
        meeting = await _create_meeting(client, host["access_token"])

        host_ws = _ws(meeting["code"], host["access_token"])
        await _connect_ready(host_ws)
        guest_ws = _ws(meeting["code"], guest["access_token"])
        await _connect_ready(guest_ws)
        await host_ws.receive_type("participant.joined")
        await host_ws.receive_type("presence.state")

        await guest_ws.send(
            _envelope("presence.update", {"mic_on": False, "hand_raised": True, "junk": "x"})
        )

        update = await host_ws.receive_type("presence.state")
        guest_entry = next(p for p in update["payload"]["participants"] if p["name"] == "Guest")
        assert guest_entry["mic_on"] is False
        assert guest_entry["hand_raised"] is True
        assert "junk" not in guest_entry

        await guest_ws.close()
        await host_ws.close()

    async def test_disconnect_announces_participant_left(self, client: AsyncClient) -> None:
        host = await _register(client, "leavehost@procto.dev", "Host")
        guest = await _register(client, "leaveguest@procto.dev", "Guest")
        meeting = await _create_meeting(client, host["access_token"])

        host_ws = _ws(meeting["code"], host["access_token"])
        await _connect_ready(host_ws)
        guest_ws = _ws(meeting["code"], guest["access_token"])
        await _connect_ready(guest_ws)
        await host_ws.receive_type("participant.joined")
        await host_ws.receive_type("presence.state")

        await guest_ws.close()

        left = await host_ws.receive_type("participant.left")
        assert left["payload"]["user_id"] == guest["user"]["id"]
        presence = await host_ws.receive_type("presence.state")
        assert [p["name"] for p in presence["payload"]["participants"]] == ["Host"]

        await host_ws.close()

    async def test_same_user_two_tabs_keep_presence(self, client: AsyncClient) -> None:
        auth = await _register(client, "tabs@procto.dev", "Tabs")
        meeting = await _create_meeting(client, auth["access_token"])

        first = _ws(meeting["code"], auth["access_token"])
        await _connect_ready(first)
        second = _ws(meeting["code"], auth["access_token"])
        await _connect_ready(second)
        await first.receive_type("presence.state")

        await second.close()

        presence = await first.receive_type("presence.state")
        assert [p["name"] for p in presence["payload"]["participants"]] == ["Tabs"]

        await first.close()
