"""Request handling logic for the Drive proxy worker.

Orchestrates auth checking, R2 cache lookups, Google Drive path
resolution, Durable Object coordination (downloader / waiter roles),
and streaming responses back to clients.

This module is intentionally decoupled from the Cloudflare entry-point
wiring so that ``entry.py`` stays a thin shell.
"""

from __future__ import annotations

from urllib.parse import unquote, urlparse

from js import Headers, Request, console
from js import Response as JsResponse
from pyodide.ffi import JsProxy
from workers import Response

from drive import download_drive_file, resolve_drive_path
from google_auth import get_access_token
from helpers import WSClient, to_js

# ---------------------------------------------------------------------------
# Public entry point — called by the Worker's fetch handler
# ---------------------------------------------------------------------------


async def handle_request(request: JsProxy, env: JsProxy) -> Response | JsResponse:
    """Top-level request handler.

    *env* is the Cloudflare Worker environment object (bindings, vars,
    secrets).  Returns a ``Response``.
    """
    try:
        return await _handle(request, env)
    except Exception as exc:
        console.error(f"Unhandled error: {exc}")
        return Response(f"Internal server error: {exc}", status=500)


# ---------------------------------------------------------------------------
# Core flow
# ---------------------------------------------------------------------------


async def _handle(request: JsProxy, env: JsProxy) -> Response | JsResponse:
    # ── Auth ─────────────────────────────────────────────────────────
    auth_header = request.headers.get("Authorization")
    expected_token: str = str(env.AUTH_TOKEN)

    if not auth_header or str(auth_header) != f"Bearer {expected_token}":
        return Response("Unauthorised", status=401)

    # ── Parse path ───────────────────────────────────────────────────
    url = urlparse(str(request.url))
    raw_path = unquote(url.path).strip("/")
    if not raw_path:
        return Response("Path required", status=400)

    # Normalise to an R2 key (lowercase, no leading slash)
    r2_key = raw_path.lower()
    path_segments = [seg for seg in raw_path.split("/") if seg]
    filename = path_segments[-1] if path_segments else "download"

    # ── R2 cache check ───────────────────────────────────────────────
    cached = await env.CACHE.head(r2_key)
    if cached:
        console.log(f"R2 cache hit: {r2_key}")
        return await _serve_from_r2(env, r2_key)

    console.log(f"R2 cache miss: {r2_key}")

    # ── Resolve Drive file ID (fast-fail on 404) ─────────────────────
    sa_json = str(env.GOOGLE_SERVICE_ACCOUNT)
    token = await get_access_token(sa_json)
    drive_root = str(env.DRIVE_ROOT_ID)

    file_info: JsProxy | None = await resolve_drive_path(
        path_segments, drive_root, token
    )
    if file_info is None:
        return Response("File not found in Google Drive", status=404)

    file_id: str = _safe_js_str(file_info.id)
    mime_type: str = _safe_js_str(file_info.mimeType, "application/octet-stream")

    # ── Coordinate via Durable Object ────────────────────────────────
    do_id: JsProxy = env.COORDINATOR.idFromName(r2_key)
    stub: JsProxy = env.COORDINATOR.get(do_id)

    ws_req: Request = Request.new(
        "http://coordinator/ws",
        to_js({"headers": to_js({"Upgrade": "websocket"})}),
    )
    do_resp: JsProxy = await stub.fetch(ws_req)
    ws: JsProxy = do_resp.webSocket
    _ = ws.accept()

    ws_client: WSClient = WSClient(ws)
    role_msg: dict[str, str] = await ws_client.recv()
    role: str | None = role_msg.get("role")

    if role == "downloader":
        return await _do_download(
            env, ws_client, r2_key, file_id, mime_type, filename, token
        )
    elif role == "waiter":
        return await _do_wait(env, ws_client, r2_key)
    else:
        ws_client.close()
        return Response(f"Unexpected role from coordinator: {role}", status=500)


# ---------------------------------------------------------------------------
# Role handlers
# ---------------------------------------------------------------------------


async def _do_download(
    env: JsProxy,
    ws_client: WSClient,
    r2_key: str,
    file_id: str,
    mime_type: str,
    filename: str,
    token: str,
) -> Response | JsResponse:
    """Downloader: fetch from Drive → stream to R2 → notify DO → serve."""
    try:
        console.log(f"Downloading Drive file {file_id} -> R2 key {r2_key}")
        drive_resp: JsResponse = await download_drive_file(file_id, token)

        # Stream the response body directly into R2 (no buffering).
        _ = await env.CACHE.put(
            r2_key,
            drive_resp.body,
            to_js(
                {
                    "httpMetadata": to_js({"contentType": mime_type}),
                    "customMetadata": to_js(
                        {
                            "filename": filename,
                            "driveFileId": file_id,
                        }
                    ),
                }
            ),
        )

        console.log(f"R2 write complete: {r2_key}")
        ws_client.send({"status": "done"})
        ws_client.close()

        return await _serve_from_r2(env, r2_key)

    except Exception as exc:
        console.error(f"Download failed for {r2_key}: {exc}")
        try:
            ws_client.send({"status": "error", "message": str(exc)})
            ws_client.close()
        except Exception:
            pass
        return Response(f"Download failed: {exc}", status=502)


async def _do_wait(
    env: JsProxy, ws_client: WSClient, r2_key: str
) -> Response | JsResponse:
    """Waiter: hold until the downloader finishes, then serve from R2."""
    console.log(f"Waiting for download: {r2_key}")
    status_msg: dict[str, str] = await ws_client.recv()
    status: str | None = status_msg.get("status")

    if status == "done":
        console.log(f"Download complete (waiter): {r2_key}")
        return await _serve_from_r2(env, r2_key)

    error: str | None = status_msg.get("message", "Download failed")
    console.error(f"Download error (waiter) for {r2_key}: {error}")
    return Response(f"Download error: {error}", status=502)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


async def _serve_from_r2(env: JsProxy, r2_key: str) -> Response | JsResponse:
    """Stream a cached file from R2 back to the client."""
    obj: JsProxy = await env.CACHE.get(r2_key)
    if not obj:
        return Response("File not found in cache", status=404)

    headers = Headers.new()
    _ = obj.writeHttpMetadata(headers)
    headers.set("Content-Length", str(obj.size))

    # Attach a Content-Disposition derived from custom metadata.
    fname: str | None = None
    try:
        if obj.customMetadata:
            fname = _safe_js_str(obj.customMetadata.filename) or None
    except Exception:
        pass
    if fname:
        safe_fname = fname.replace('"', '\\"')
        headers.set(
            "Content-Disposition",
            f'inline; filename="{safe_fname}"',
        )

    return JsResponse.new(obj.body, to_js({"status": 200, "headers": headers}))


def _safe_js_str(js_val: object, default: str = "") -> str:
    """Convert a JS value to a Python string, returning *default* for
    ``undefined``, ``null`` and other falsy sentinels."""
    try:
        s = str(js_val)
        if s in ("undefined", "null", "None", ""):
            return default
        return s
    except Exception:
        return default
