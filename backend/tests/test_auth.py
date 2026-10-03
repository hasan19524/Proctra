"""Authentication end-to-end tests (Phase 2)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from httpx import AsyncClient

from app.core.config import settings

REGISTER_PAYLOAD = {
    "email": "hasan@procto.dev",
    "password": "correct-horse-1",
    "display_name": "Hasan",
}


async def _register(client: AsyncClient) -> dict[str, Any]:
    response = await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    assert response.status_code == 201, response.text
    data: dict[str, Any] = response.json()
    return data


async def _login(client: AsyncClient, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "email": REGISTER_PAYLOAD["email"],
        "password": REGISTER_PAYLOAD["password"],
    }
    payload.update(overrides)
    response = await client.post("/api/v1/auth/login", json=payload)
    data: dict[str, Any] = response.json()
    return {**data, "_status": response.status_code}


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestRegister:
    async def test_register_returns_user_and_sets_cookie(self, client: AsyncClient) -> None:
        data = await _register(client)

        assert data["token_type"] == "bearer"
        assert data["expires_in"] == settings.access_token_ttl_minutes * 60
        assert data["user"]["email"] == REGISTER_PAYLOAD["email"]
        assert data["user"]["display_name"] == "Hasan"
        assert "procto_refresh" in client.cookies

        me = await client.get("/api/v1/auth/me", headers=_auth(data["access_token"]))
        assert me.status_code == 200
        assert me.json()["email"] == REGISTER_PAYLOAD["email"]

    async def test_duplicate_email_conflicts(self, client: AsyncClient) -> None:
        await _register(client)
        second = await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
        assert second.status_code == 409

    async def test_short_password_rejected_by_validation(self, client: AsyncClient) -> None:
        payload = REGISTER_PAYLOAD | {"password": "short"}
        response = await client.post("/api/v1/auth/register", json=payload)
        assert response.status_code == 422

    async def test_missing_fields_rejected(self, client: AsyncClient) -> None:
        response = await client.post("/api/v1/auth/register", json={"email": "a@b.co"})
        assert response.status_code == 422


class TestLogin:
    async def test_login_success(self, client: AsyncClient) -> None:
        await _register(client)
        client.cookies.clear()

        data = await _login(client)
        assert data["_status"] == 200
        assert data["user"]["email"] == REGISTER_PAYLOAD["email"]
        assert "procto_refresh" in client.cookies

    async def test_wrong_password_and_unknown_email_are_uniform(self, client: AsyncClient) -> None:
        await _register(client)
        client.cookies.clear()

        wrong_password = await client.post(
            "/api/v1/auth/login",
            json={"email": REGISTER_PAYLOAD["email"], "password": "not-the-password"},
        )
        unknown_email = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@procto.dev", "password": "whatever-123"},
        )

        assert wrong_password.status_code == unknown_email.status_code == 401
        assert wrong_password.json()["detail"] == unknown_email.json()["detail"]

    async def test_email_is_case_insensitive(self, client: AsyncClient) -> None:
        await _register(client)
        client.cookies.clear()

        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": REGISTER_PAYLOAD["email"].upper(),
                "password": REGISTER_PAYLOAD["password"],
            },
        )
        assert response.status_code == 200


class TestMe:
    async def test_requires_authentication(self, client: AsyncClient) -> None:
        assert (await client.get("/api/v1/auth/me")).status_code == 401

    async def test_rejects_garbage_token(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/auth/me", headers=_auth("not-a-jwt"))
        assert response.status_code == 401

    async def test_rejects_expired_token(self, client: AsyncClient) -> None:
        await _register(client)
        expired = jwt.encode(
            {
                "sub": "00000000-0000-0000-0000-000000000000",
                "type": "access",
                "iat": datetime.now(UTC) - timedelta(hours=1),
                "exp": datetime.now(UTC) - timedelta(minutes=30),
            },
            settings.secret_key,
            algorithm=settings.jwt_algorithm,
        )
        response = await client.get("/api/v1/auth/me", headers=_auth(expired))
        assert response.status_code == 401

    async def test_rejects_refresh_jwt_used_as_access(self, client: AsyncClient) -> None:
        await _register(client)
        wrong_type = jwt.encode(
            {
                "sub": "00000000-0000-0000-0000-000000000000",
                "type": "refresh",
                "iat": datetime.now(UTC),
                "exp": datetime.now(UTC) + timedelta(minutes=5),
            },
            settings.secret_key,
            algorithm=settings.jwt_algorithm,
        )
        response = await client.get("/api/v1/auth/me", headers=_auth(wrong_type))
        assert response.status_code == 401


class TestRefresh:
    async def test_refresh_rotates_tokens(self, client: AsyncClient) -> None:
        first = await _register(client)
        old_refresh = client.cookies.get("procto_refresh")
        assert old_refresh

        refreshed = await client.post("/api/v1/auth/refresh")
        assert refreshed.status_code == 200
        data = refreshed.json()
        assert data["access_token"] != first["access_token"]
        assert client.cookies.get("procto_refresh") != old_refresh

        me = await client.get("/api/v1/auth/me", headers=_auth(data["access_token"]))
        assert me.status_code == 200

    async def test_reuse_detection_revokes_family(self, client: AsyncClient) -> None:
        await _register(client)
        stolen = client.cookies.get("procto_refresh")
        assert stolen

        # First rotation succeeds and issues a new refresh token.
        ok = await client.post("/api/v1/auth/refresh")
        assert ok.status_code == 200
        rotated = client.cookies.get("procto_refresh")
        assert rotated and rotated != stolen

        # Replaying the revoked token fails...
        client.cookies.set("procto_refresh", stolen)
        replay = await client.post("/api/v1/auth/refresh")
        assert replay.status_code == 401

        # ...and the previously rotated token is dead too (family revocation).
        client.cookies.set("procto_refresh", rotated)
        after_reuse = await client.post("/api/v1/auth/refresh")
        assert after_reuse.status_code == 401

    async def test_refresh_without_cookie_is_401(self, client: AsyncClient) -> None:
        response = await client.post("/api/v1/auth/refresh")
        assert response.status_code == 401

    async def test_refresh_with_unknown_token_is_401(self, client: AsyncClient) -> None:
        client.cookies.set("procto_refresh", "made-up-token")
        response = await client.post("/api/v1/auth/refresh")
        assert response.status_code == 401


class TestLogout:
    async def test_logout_revokes_session(self, client: AsyncClient) -> None:
        await _register(client)
        refresh_value = client.cookies.get("procto_refresh")
        assert refresh_value

        logout = await client.post("/api/v1/auth/logout")
        assert logout.status_code == 200
        assert "procto_refresh" not in client.cookies

        # The revoked value no longer works even if presented again.
        client.cookies.set("procto_refresh", refresh_value)
        refresh = await client.post("/api/v1/auth/refresh")
        assert refresh.status_code == 401

    async def test_logout_all_revokes_every_session(self, client: AsyncClient) -> None:
        await _register(client)
        data = await _login(client)
        second_refresh = client.cookies.get("procto_refresh")

        # Two independent sessions for the same user.
        client.cookies.clear()
        await _login(client)
        first_refresh = client.cookies.get("procto_refresh")
        assert first_refresh and second_refresh and first_refresh != second_refresh

        response = await client.post("/api/v1/auth/logout-all", headers=_auth(data["access_token"]))
        assert response.status_code == 200

        for token in (first_refresh, second_refresh):
            client.cookies.delete("procto_refresh")
            client.cookies.set("procto_refresh", token)
            assert (await client.post("/api/v1/auth/refresh")).status_code == 401


class TestRateLimit:
    async def test_login_attempts_rate_limited(self, client: AsyncClient) -> None:
        await _register(client)
        statuses = []
        for _ in range(12):
            response = await client.post(
                "/api/v1/auth/login",
                json={"email": REGISTER_PAYLOAD["email"], "password": "wrong-password"},
            )
            statuses.append(response.status_code)

        assert statuses[-1] == 429
        assert statuses[0] in (401, 429)
