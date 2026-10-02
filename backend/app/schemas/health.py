"""Pydantic response/request contracts, grouped by domain."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Liveness payload."""

    status: Literal["ok"] = "ok"
    service: str
    version: str
    environment: str
    time: datetime


class ReadinessResponse(BaseModel):
    """Readiness payload with per-dependency status."""

    status: Literal["ready", "degraded"]
    checks: dict[str, Literal["up", "down"]] = Field(default_factory=dict)
    time: datetime
