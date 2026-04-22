"""FFI helpers for Python Workers."""

import asyncio
import json
from typing import cast

from js import Object, WebSocket
from pyodide.ffi import JsProxy, create_proxy
from pyodide.ffi import to_js as _to_js


def to_js(obj: object) -> JsProxy:
    """Convert a Python object to a JavaScript object.

    Uses ``Object.fromEntries`` so that Python dicts become plain JS objects
    (rather than ``Map`` instances which most Workers APIs won't accept).
    """
    return _to_js(obj, dict_converter=Object.fromEntries)


class WSClient:
    """Thin async wrapper around a Worker-side WebSocket connection.

    Messages received from the server are placed on an ``asyncio.Queue`` so
    that the calling coroutine can simply ``await ws_client.recv()``.
    """

    def __init__(self, ws: WebSocket | JsProxy) -> None:
        self.ws: WebSocket | JsProxy = ws
        self._queue: asyncio.Queue[dict[str, str]] = asyncio.Queue()

        # We must prevent the Python callbacks from being garbage-collected
        # while the JS event listeners still reference them.
        self._msg_proxy: JsProxy = create_proxy(self._on_message)
        self._close_proxy: JsProxy = create_proxy(self._on_close)
        self._error_proxy: JsProxy = create_proxy(self._on_error)

        _ = ws.addEventListener("message", self._msg_proxy)
        _ = ws.addEventListener("close", self._close_proxy)
        _ = ws.addEventListener("error", self._error_proxy)

    # -- internal callbacks ---------------------------------------------------

    def _on_message(self, event: JsProxy) -> None:
        try:
            data: dict[str, str] = cast(dict[str, str], json.loads(str(event.data)))
        except (json.JSONDecodeError, Exception):
            data = {"raw": str(event.data)}
        self._queue.put_nowait(data)

    def _on_close(self, event: JsProxy) -> None:
        self._queue.put_nowait(
            {
                "status": "error",
                "message": (
                    f"WebSocket closed unexpectedly: "
                    f"code={event.code} reason={event.reason}"
                ),
            }
        )

    def _on_error(self, _event: JsProxy) -> None:
        self._queue.put_nowait({"status": "error", "message": "WebSocket error"})

    # -- public API -----------------------------------------------------------

    async def recv(self) -> dict[str, str]:
        """Block until the next JSON message arrives."""
        return await self._queue.get()

    def send(self, data: dict[str, str]) -> None:
        """Send a JSON-serialisable *data* dict over the WebSocket."""
        _ = self.ws.send(json.dumps(data))

    def close(self, code: int = 1000, reason: str = "") -> None:
        """Close the WebSocket connection."""
        try:
            _ = self.ws.close(code, reason)
        except Exception:
            pass
