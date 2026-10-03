"""Minimal async ASGI WebSocket test client.

Drives the FastAPI app directly inside the pytest-asyncio event loop (the
sync Starlette TestClient would need its own loop and fight the async DB/
Redis fixtures). Frames are exchanged through two asyncio queues.
"""

import asyncio
import json
from collections.abc import Callable
from typing import Any

WS_PATH_TYPE = "websocket"


class WsDisconnect(Exception):
    """Raised when the server closed the socket."""

    def __init__(self, code: int | None) -> None:
        super().__init__(f"server closed with code {code}")
        self.code = code


class WsTestClient:
    """One WebSocket connection against the ASGI app."""

    def __init__(self, app: Any, path: str, query: dict[str, str] | None = None) -> None:
        self._app = app
        self._inbound: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._outbound: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        from urllib.parse import urlencode

        qs = urlencode(query or {})
        self._scope: dict[str, Any] = {
            "type": WS_PATH_TYPE,
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "scheme": "ws",
            "method": "GET",
            "path": path,
            "raw_path": path.encode(),
            "query_string": qs.encode(),
            "root_path": "",
            "headers": [(b"host", b"testserver")],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "subprotocols": [],
            "state": {},
        }
        self._task: asyncio.Task[None] | None = None
        self.close_code: int | None = None

    async def _app_receive(self) -> dict[str, Any]:
        return await self._inbound.get()

    async def _app_send(self, message: dict[str, Any]) -> None:
        await self._outbound.put(message)

    async def connect(self, timeout: float = 5.0) -> None:
        """Perform the handshake; raises WsDisconnect when rejected."""
        self._task = asyncio.create_task(self._app(self._scope, self._app_receive, self._app_send))
        await self._inbound.put({"type": "websocket.connect"})
        message = await asyncio.wait_for(self._outbound.get(), timeout=timeout)
        if message["type"] == "websocket.close":
            raise WsDisconnect(message.get("code"))
        if message["type"] != "websocket.accept":
            raise AssertionError(f"unexpected handshake frame: {message}")

    async def send(self, frame: dict[str, Any] | str) -> None:
        """Send a client frame (dict is JSON-encoded)."""
        text = frame if isinstance(frame, str) else json.dumps(frame)
        await self._inbound.put({"type": "websocket.receive", "text": text})

    async def receive(self, timeout: float = 5.0) -> dict[str, Any]:
        """Next server frame as a dict; raises WsDisconnect once closed."""
        message = await asyncio.wait_for(self._outbound.get(), timeout=timeout)
        if message["type"] == "websocket.close":
            self.close_code = message.get("code")
            raise WsDisconnect(self.close_code)
        if message["type"] == "websocket.send":
            frame: dict[str, Any] = json.loads(message["text"])
            return frame
        raise AssertionError(f"unexpected outbound frame: {message}")

    async def receive_type(
        self,
        frame_type: str,
        timeout: float = 5.0,
        where: Callable[[dict[str, Any]], bool] | None = None,
    ) -> dict[str, Any]:
        """Pop frames until one of ``frame_type`` arrives (others discarded).

        ``where`` optionally filters on the frame payload (e.g. ignore the
        first presence.state and wait for the one with our flag set).
        """
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError(f"no {frame_type} frame within {timeout}s")
            frame = await self.receive(timeout=remaining)
            if frame["type"] == frame_type and (where is None or where(frame)):
                return frame

    async def close(self) -> None:
        """Disconnect and wait for the server handler to finish cleanup."""
        if self._task is None:
            return
        await self._inbound.put({"type": "websocket.disconnect", "code": 1000})
        await asyncio.wait_for(self._task, timeout=5.0)
        self._task = None
