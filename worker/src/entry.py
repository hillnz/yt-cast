"""Cloudflare Worker entry point.

Keeps Cloudflare-specific wiring in one place — the ``Default`` class is the
fetch handler and the ``Coordinator`` import ensures wrangler can discover the
Durable Object class.
"""

from __future__ import annotations

from js import Response as JsResponse
from js import console
from pyodide.ffi import JsProxy
from workers import Response, WorkerEntrypoint

# Re-export so wrangler can find the DO class via the entry module.
from coordinator import Coordinator  # noqa: F401
from handler import handle_request

__all__ = ["Coordinator", "Default"]


class Default(WorkerEntrypoint):
    """Thin shell that delegates to :func:`handler.handle_request`."""

    async def fetch(self, request: JsProxy) -> Response | JsResponse:
        try:
            return await handle_request(request, self.env)
        except Exception as exc:
            console.error(f"Unhandled error: {exc}")
            return Response(f"Internal server error: {exc}", status=500)
