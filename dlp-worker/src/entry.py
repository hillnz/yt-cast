"""Cloudflare Worker entry point.

Keeps Cloudflare-specific wiring in one place — the ``Default`` class
bridges the Workers fetch handler to the FastAPI ASGI application.
"""

from __future__ import annotations

import asgi
from pyodide.ffi import JsProxy
from workers import WorkerEntrypoint

# Re-export so wrangler can find the DO class via the entry module.
from coordinator import Coordinator  # noqa: F401
from handler import app

__all__ = ["Coordinator", "Default"]


class Default(WorkerEntrypoint):
    """Thin shell that delegates to the FastAPI app via ASGI."""

    async def fetch(self, request: JsProxy):
        return await asgi.fetch(app, request, self.env)
