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
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import cast

from js import Request as JsRequest
from js import WebSocket, WebSocketPair, console
from pyodide.ffi import JsProxy
from workers import DurableObject, Response

from helpers import WSClient, to_js


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


# ---------------------------------------------------------------------------
# Client-side helpers
# ---------------------------------------------------------------------------


class CoordinatorSession:
    """Active session with a Coordinator DO.

    Exposes the assigned role and a ``wait()`` helper for waiters.  Status
    signalling (``done`` / ``error``) and socket teardown are handled by the
    surrounding :func:`coordinate` context manager — callers should not need
    to touch the underlying WebSocket.
    """

    def __init__(self, ws_client: WSClient, role: str) -> None:
        self._ws: WSClient = ws_client
        self.role: str = role

    @property
    def is_downloader(self) -> bool:
        return self.role == "downloader"

    @property
    def is_waiter(self) -> bool:
        return self.role == "waiter"

    async def wait(self) -> None:
        """Block until the downloader signals completion.

        Raises
        ------
        RuntimeError
            If the downloader reports an error or disconnects unexpectedly.
        """
        status_msg: dict[str, str] = await self._ws.recv()
        status: str | None = status_msg.get("status")
        if status == "done":
            return
        message: str = status_msg.get("message", "Download failed")
        raise RuntimeError(message)


@asynccontextmanager
async def coordinate(env: JsProxy, key: str) -> AsyncGenerator[CoordinatorSession]:
    """Open a coordinated session with the Coordinator DO for *key*.

    The first caller for a given key is assigned the ``downloader`` role and
    is expected to perform the work inside the ``async with`` block.  All
    subsequent callers are assigned ``waiter`` and should call
    :meth:`CoordinatorSession.wait` (which blocks until the downloader
    finishes).

    Status signalling is automatic:

    * Clean exit from the ``async with`` block (downloader) → sends
      ``{"status": "done"}`` to the DO.
    * Exception inside the block (downloader) → sends
      ``{"status": "error", "message": str(exc)}`` and re-raises.
    * Waiters never send status; the DO only reads from the downloader.

    The WebSocket is always closed on exit.
    """
    do_id: JsProxy = env.COORDINATOR.idFromName(key)
    stub: JsProxy = env.COORDINATOR.get(do_id)

    ws_req = JsRequest.new(
        "http://coordinator/ws",
        to_js({"headers": to_js({"Upgrade": "websocket"})}),
    )
    do_resp: JsProxy = await stub.fetch(ws_req)
    ws: JsProxy = do_resp.webSocket
    _ = ws.accept()

    ws_client = WSClient(ws)
    role_msg: dict[str, str] = await ws_client.recv()
    role: str | None = role_msg.get("role")

    if role not in ("downloader", "waiter"):
        ws_client.close()
        raise RuntimeError(f"Unexpected role from coordinator: {role}")

    session = CoordinatorSession(ws_client, role)
    try:
        yield session
    except Exception as exc:
        if session.is_downloader:
            try:
                ws_client.send({"status": "error", "message": str(exc)})
            except Exception:
                pass
        raise
    else:
        if session.is_downloader:
            ws_client.send({"status": "done"})
    finally:
        ws_client.close()
