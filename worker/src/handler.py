"""FastAPI application for the Drive proxy worker.

This module focuses on HTTP concerns: routing, request parsing,
exception handling, and shaping responses (including streaming from
R2). The work of resolving Drive paths, coordinating concurrent
downloads, and populating the R2 cache lives in ``serve.py``.
"""

from __future__ import annotations

from typing import AsyncIterator, cast

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse, StreamingResponse
from js import Headers, Uint8Array, console
from pyodide.ffi import JsProxy

from serve import DownloadError, NotFoundError, ensure_cached

app = FastAPI()

# ---------------------------------------------------------------------------
# Exception handling
# ---------------------------------------------------------------------------


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    console.error(f"Unhandled error: {exc}")
    return PlainTextResponse(f"Internal server error: {exc}", status_code=500)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/{path:path}")
async def handle(request: Request, path: str):
    """Resolve a Drive path, ensure it's cached in R2, and stream it back."""
    if not path:
        raise HTTPException(status_code=400, detail="Path required")

    env = request.scope["env"]

    try:
        result = await ensure_cached(env, path)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DownloadError as exc:
        return PlainTextResponse(f"Download failed: {exc}", status_code=502)

    return await _serve_from_r2(env, result.r2_key)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


async def _stream_readable(body: JsProxy) -> AsyncIterator[bytes]:
    """Yield chunks from a JS ``ReadableStream`` as Python bytes."""
    reader = body.getReader()
    try:
        while True:
            result = await reader.read()
            if result.done:
                break
            chunk = cast(Uint8Array, result.value)
            yield chunk.to_bytes()
    finally:
        reader.releaseLock()


async def _serve_from_r2(env: JsProxy, r2_key: str) -> StreamingResponse:
    """Stream a cached file from R2 back to the client."""
    obj: JsProxy = await env.CACHE.get(r2_key)
    if not obj:
        raise HTTPException(status_code=404, detail="File not found in cache")

    # Use writeHttpMetadata to extract content-type and friends.
    js_headers = Headers.new()
    _ = obj.writeHttpMetadata(js_headers)
    content_type = js_headers.get("content-type") or "application/octet-stream"

    headers: dict[str, str] = {"Content-Length": str(obj.size)}

    # Attach a Content-Disposition derived from custom metadata.
    fname: str | None = None
    try:
        custom = obj.customMetadata
        if custom and custom.filename:
            fname = str(custom.filename)
    except Exception:
        pass
    if fname:
        safe_fname = fname.replace('"', '\\"')
        headers["Content-Disposition"] = f'inline; filename="{safe_fname}"'

    return StreamingResponse(
        _stream_readable(obj.body),
        media_type=content_type,
        headers=headers,
    )
