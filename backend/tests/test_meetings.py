"""Meeting creation/lookup tests (Phase 3)."""

import re
from typing import Any

from httpx import AsyncClient

from app.services.meeting_service import CODE_ALPHABET, CODE_GROUP

CODE_PATTERN = re.compile(
    rf"^[{CODE_ALPHABET}]{{{CODE_GROUP}}}-[{CODE_ALPHABET}]{{{CODE_GROUP}}}-"
    rf"[{CODE_ALPHABET}]{{{CODE_GROUP}}}$"
)

REGISTER_PAYLOAD = {
    "email": "host@procto.dev",
    "password": "correct-horse-1",
    "display_name": "Host",
}


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _register(client: AsyncClient) -> dict[str, Any]:
    response = await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    assert response.status_code == 201, response.text
    data: dict[str, Any] = response.json()
    return data


class TestCreateMeeting:
    async def test_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.post("/api/v1/meetings", json={})
        assert response.status_code == 401

    async def test_creates_meeting_with_human_friendly_code(self, client: AsyncClient) -> None:
        auth = await _register(client)

        response = await client.post(
            "/api/v1/meetings",
            json={"title": "Sprint planning"},
            headers=_auth(auth["access_token"]),
        )

        assert response.status_code == 201, response.text
        data = response.json()
        assert CODE_PATTERN.match(data["code"]), data["code"]
        assert data["title"] == "Sprint planning"
        assert data["status"] == "waiting"
        assert data["is_locked"] is False
        assert data["host_id"] == auth["user"]["id"]

    async def test_title_is_optional(self, client: AsyncClient) -> None:
        auth = await _register(client)

        response = await client.post(
            "/api/v1/meetings",
            json={},
            headers=_auth(auth["access_token"]),
        )

        assert response.status_code == 201, response.text
        assert response.json()["title"] is None

    async def test_rejects_too_long_title(self, client: AsyncClient) -> None:
        auth = await _register(client)

        response = await client.post(
            "/api/v1/meetings",
            json={"title": "x" * 121},
            headers=_auth(auth["access_token"]),
        )

        assert response.status_code == 422

    async def test_two_meetings_get_distinct_codes(self, client: AsyncClient) -> None:
        auth = await _register(client)
        headers = _auth(auth["access_token"])

        first = await client.post("/api/v1/meetings", json={}, headers=headers)
        second = await client.post("/api/v1/meetings", json={}, headers=headers)

        assert first.json()["code"] != second.json()["code"]


class TestGetMeeting:
    async def test_lookup_by_code(self, client: AsyncClient) -> None:
        auth = await _register(client)
        headers = _auth(auth["access_token"])
        created = await client.post("/api/v1/meetings", json={"title": "Daily"}, headers=headers)
        code = created.json()["code"]

        response = await client.get(f"/api/v1/meetings/{code}", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == code
        assert data["title"] == "Daily"

    async def test_lookup_is_case_insensitive(self, client: AsyncClient) -> None:
        auth = await _register(client)
        headers = _auth(auth["access_token"])
        created = await client.post("/api/v1/meetings", json={}, headers=headers)
        code = created.json()["code"]

        response = await client.get(f"/api/v1/meetings/{code.upper()}", headers=headers)
        assert response.status_code == 200
        assert response.json()["code"] == code

    async def test_unknown_code_is_404(self, client: AsyncClient) -> None:
        auth = await _register(client)

        response = await client.get(
            "/api/v1/meetings/zzz-zzz-zzz",
            headers=_auth(auth["access_token"]),
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Meeting not found"

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/meetings/abc-def-ghi")
        assert response.status_code == 401
