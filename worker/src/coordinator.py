"""Coordinator Durable Object.

Uses the WebSocket Hibernation API to ensure exactly one Worker downloads
a given file at a time.  The DO does NOT perform the download — it only
assigns roles (``downloader`` or ``waiter``) and relays status messages.

Lifecycle
---------
1. First WebSocket connects  → assigned ``downloader`` tag.
2. Subsequent connects       → assigned ``waiter`` tag.
3. Downloader sends ``done`` → broadcast to waiters, close all, clean up.
4. Downloader sends ``error``→ broadcast to waiters, close all, clean up.
5. Downloader disconnects    → treat as error, notify waiters, clean up.
6. All sockets closed        → DO hibernates, eventually evicts.
"""

import json
from typing import cast

from js import Request as JsRequest
from js import WebSocket, WebSocketPair, console
from pyodide.ffi import JsProxy
from workers import DurableObject, Response

from helpers import to_js


class Coordinator(DurableObject):
    """Coordinate file downloads via WebSocket Hibernation.

    Roles
    -----
    downloader — first connection; responsible for fetching from Drive
                 and streaming into R2.
    waiter     — subsequent connections; hold until the downloader
                 reports success or failure.
    """

    # -- HTTP handler (WebSocket upgrade) ------------------------------------

    async def fetch(self, request: JsRequest) -> Response:
        upgrade: str | None = request.headers.get("Upgrade")
        if not upgrade or str(upgrade).lower() != "websocket":
            return Response("Expected WebSocket upgrade", status=400)

        pair = WebSocketPair.new()
        client: WebSocket
        server: WebSocket
        client, server = pair.object_values()

        # Check whether a downloader is already active
        downloaders: JsProxy = self.ctx.getWebSockets("downloader")
        has_downloader = bool(downloaders and downloaders.length > 0)

        if not has_downloader:
            self.ctx.acceptWebSocket(server, to_js(["downloader"]))
            _ = server.send(json.dumps({"role": "downloader"}))
            console.log("[Coordinator] Assigned role: downloader")
        else:
            self.ctx.acceptWebSocket(server, to_js(["waiter"]))
            _ = server.send(json.dumps({"role": "waiter"}))
            console.log("[Coordinator] Assigned role: waiter")

        return Response(None, status=101, web_socket=client)

    # -- Hibernation handlers ------------------------------------------------

    async def webSocketMessage(self, _ws: WebSocket, message: str | bytes) -> None:
        """Handle status messages from the downloader."""
        try:
            data = cast(dict[str, str], json.loads(str(message)))
        except json.JSONDecodeError:
            return

        status: str | None = data.get("status")
        if status in ("done", "error"):
            # Broadcast the raw message to every waiter
            n = self._broadcast_to_waiters(str(message))
            console.log(f"[Coordinator] status={status}, notified {n} waiter(s)")
            await self._cleanup()

    async def webSocketClose(
        self, _ws: WebSocket, _code: int, _reason: str, _was_clean: bool
    ) -> None:
        """Handle unexpected WebSocket closure.

        By the time this handler fires the closed socket has already been
        removed from ``getWebSockets()``.  If the downloader list is now
        empty, the *downloader* was the one that disconnected.
        """
        downloaders: JsProxy = self.ctx.getWebSockets("downloader")
        if downloaders and downloaders.length > 0:
            # A waiter dropped off — nothing to do.
            return

        # Downloader disappeared — tell every remaining waiter.
        error_msg = json.dumps(
            {
                "status": "error",
                "message": "Downloader disconnected unexpectedly",
            }
        )
        _ = self._broadcast_to_waiters(error_msg)
        console.error("[Coordinator] Downloader disconnected unexpectedly")
        await self._cleanup()

    async def webSocketError(self, _ws: WebSocket, _error: JsProxy) -> None:
        """Treat errors identically to an unexpected close."""
        await self.webSocketClose(_ws, 1011, "WebSocket error", False)

    # -- Internal helpers ----------------------------------------------------

    def _broadcast_to_waiters(self, message: str) -> int:
        """Send *message* to every waiter socket.  Returns the count sent."""
        waiters: JsProxy = self.ctx.getWebSockets("waiter")
        n: int = 0
        if waiters:
            for waiter in waiters:
                try:
                    _ = waiter.send(message)
                    n += 1
                except Exception:
                    pass
        return n

    async def _cleanup(self) -> None:
        """Close every socket and wipe stored state."""
        all_sockets: JsProxy = self.ctx.getWebSockets()
        if all_sockets:
            for ws in all_sockets:
                try:
                    _ = ws.close(1000, "complete")
                except Exception:
                    pass
        await self.ctx.storage.deleteAll()
