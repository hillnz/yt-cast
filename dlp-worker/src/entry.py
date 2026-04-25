"""Cloudflare Worker entry point."""

from __future__ import annotations

import asgi
from pyodide.ffi import JsProxy
from workers import WorkerEntrypoint

from handler import app

__all__ = ["Default"]


class Default(WorkerEntrypoint):
    """Thin shell that delegates to the FastAPI app via ASGI."""

    async def fetch(self, request: JsProxy):
        return await asgi.fetch(app, request, self.env)
