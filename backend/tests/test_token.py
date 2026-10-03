"""LiveKit token tests (Phase 9): grants, and the same lock/end gate as the WS."""

import warnings
from typing import Any

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.db import SessionLocal
from app.models.meeting import Meeting
from tests.test_ws import _create_meeting, _register

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")


async def _mint(client: AsyncClient, token: str, code: str) -> tuple[int, dict[str, Any]]:
    r = await client.post(
        f"/api/v1/meetings/{code}/token", headers={"Authorization": f"Bearer {token}"}
    )
    return r.status_code, (r.json() if r.status_code == 200 else {})


def _decode(token: str) -> dict[str, Any]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return jwt.decode(
            token,
            settings.livekit_api_secret,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )


class TestMintToken:
    async def test_mints_room_grants_for_the_member(self, client: AsyncClient) -> None:
        host = await _register(client, "lhost@procto.dev", "Live Host")
        meeting = await _create_meeting(client, host["access_token"])

        status_code, body = await _mint(client, host["access_token"], meeting["code"])
        assert status_code == 200
        assert body["url"] == settings.livekit_url

        claims = _decode(body["token"])
        assert claims["sub"] == host["user"]["id"]
        assert claims["name"] == "Live Host"
        grants = claims["video"]
        assert grants["room"] == meeting["code"]
        assert grants["roomJoin"] is True
        assert grants["canPublish"] is True
        assert grants["canSubscribe"] is True

    async def test_requires_auth_and_unknown_codes_404(self, client: AsyncClient) -> None:
        host = await _register(client, "lhost2@procto.dev", "Live Host 2")
        meeting = await _create_meeting(client, host["access_token"])

        r = await client.post(f"/api/v1/meetings/{meeting['code']}/token")
        assert r.status_code == 401

        status_code, _ = await _mint(client, host["access_token"], "zzz-zzz-zzz")
        assert status_code == 404

    async def test_ended_meeting_is_403(self, client: AsyncClient) -> None:
        host = await _register(client, "lhost3@procto.dev", "Live Host 3")
        meeting = await _create_meeting(client, host["access_token"])
        async with SessionLocal() as session:
            row = await session.scalar(select(Meeting).where(Meeting.id == meeting["id"]))
            assert row is not None
            row.status = "ended"
            await session.commit()

        status_code, _ = await _mint(client, host["access_token"], meeting["code"])
        assert status_code == 403

    async def test_locked_meeting_blocks_guest_but_not_host(self, client: AsyncClient) -> None:
        host = await _register(client, "lhost4@procto.dev", "Live Host 4")
        guest = await _register(client, "lguest@procto.dev", "Live Guest")
        meeting = await _create_meeting(client, host["access_token"])
        async with SessionLocal() as session:
            row = await session.scalar(select(Meeting).where(Meeting.id == meeting["id"]))
            assert row is not None
            row.is_locked = True
            await session.commit()

        status_code, _ = await _mint(client, guest["access_token"], meeting["code"])
        assert status_code == 403

        status_code, body = await _mint(client, host["access_token"], meeting["code"])
        assert status_code == 200
        assert _decode(body["token"])["video"]["room"] == meeting["code"]
