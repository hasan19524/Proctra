"""Versioned JSON frame envelope for the app WebSocket (REALTIME.md §1).

Every frame is ``{"v", "type", "id", "ts", "payload"}`` with an optional
server-assigned ``seq`` for durable events.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

PROTOCOL_VERSION = 1

# Hard cap on one client frame's UTF-8 size. Notes cap at ~100 KB of JSON, so
# this leaves headroom while bounding a single oversized payload (DoS guard).
MAX_FRAME_BYTES = 256 * 1024

# Application close codes (4000-4999 range, machine-readable).
CLOSE_UNAUTHORIZED = 4001
CLOSE_FORBIDDEN = 4003
CLOSE_NOT_FOUND = 4004
CLOSE_PROTOCOL_ERROR = 4008
CLOSE_IDLE_TIMEOUT = 4013


class ProtocolError(Exception):
    """A malformed or unsupported client frame."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class ClientFrame:
    """A parsed client → server frame."""

    type: str
    payload: dict[str, Any]
    id: str | None = None


def server_frame(
    frame_type: str,
    payload: dict[str, Any] | None = None,
    *,
    seq: int | None = None,
    frame_id: str | None = None,
) -> str:
    """Serialize a server → client frame to JSON text."""
    frame: dict[str, Any] = {
        "v": PROTOCOL_VERSION,
        "type": frame_type,
        "id": frame_id or str(uuid.uuid4()),
        "ts": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "payload": payload or {},
    }
    if seq is not None:
        frame["seq"] = seq
    return json.dumps(frame, separators=(",", ":"))


def parse_client_frame(raw: str) -> ClientFrame:
    """Parse and validate a raw client frame.

    Raises ``ProtocolError`` with a machine-readable code on any malformed
    input so the gateway can answer with an ``error`` frame instead of dying.
    """
    if len(raw.encode("utf-8", "ignore")) > MAX_FRAME_BYTES:
        raise ProtocolError("frame_too_large", "Frame exceeds size limit")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProtocolError("bad_json", "Frame is not valid JSON") from exc

    if not isinstance(data, dict):
        raise ProtocolError("bad_envelope", "Frame must be a JSON object")

    version = data.get("v")
    if version != PROTOCOL_VERSION:
        raise ProtocolError("bad_version", f"Unsupported protocol version: {version!r}")

    frame_type = data.get("type")
    if not isinstance(frame_type, str) or not frame_type:
        raise ProtocolError("bad_envelope", "Frame is missing a type")

    payload = data.get("payload", {})
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise ProtocolError("bad_envelope", "payload must be an object")

    frame_id = data.get("id")
    if frame_id is not None and not isinstance(frame_id, str):
        raise ProtocolError("bad_envelope", "id must be a string")

    return ClientFrame(type=frame_type, payload=payload, id=frame_id)
