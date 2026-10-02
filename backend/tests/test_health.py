"""API-level tests for the health endpoints (Phase 0)."""

from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_ok() -> None:
    """Liveness endpoint answers 200 without touching any dependency."""
    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "procto-backend"
    assert payload["version"]
    assert payload["environment"]
    assert payload["time"]


def test_readiness_reports_dependency_status() -> None:
    """Readiness returns a structured payload; 503 only when degraded."""
    with TestClient(app) as client:
        response = client.get("/api/health/ready")

    assert response.status_code in (200, 503)
    payload = response.json()
    assert payload["status"] in ("ready", "degraded")
    assert set(payload["checks"]) == {"database", "redis"}
    assert all(value in ("up", "down") for value in payload["checks"].values())

    if response.status_code == 200:
        assert payload["status"] == "ready"
        assert all(value == "up" for value in payload["checks"].values())
    else:
        assert payload["status"] == "degraded"


def test_openapi_document_is_served() -> None:
    """Interactive API docs are available outside production."""
    with TestClient(app) as client:
        response = client.get("/api/openapi.json")

    assert response.status_code == 200
    assert "/api/health" in response.json()["paths"]
