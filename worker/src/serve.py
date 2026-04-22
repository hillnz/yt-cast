"""Core serving logic for the Drive proxy worker.

Encapsulates the work of ensuring a Drive-backed file is present in
the R2 cache: resolving the path against Google Drive, coordinating
concurrent requests via a Durable Object, and writing the downloaded
bytes back into R2.

HTTP concerns (request parsing, response shaping, status codes) live
in ``handler.py`` — this module stays framework-agnostic and raises
typed errors that the handler maps onto HTTP responses.
"""

from __future__ import annotations

from dataclasses import dataclass

from js import console
from pyodide.ffi import JsProxy

from coordinator import coordinate
from drive import download_drive_file, resolve_drive_path
from google_auth import get_access_token
from helpers import to_js


class ServeError(Exception):
    """Base class for errors raised while populating the R2 cache."""


class NotFoundError(ServeError):
    """Raised when the requested path does not exist in Google Drive."""


class DownloadError(ServeError):
    """Raised when the file could not be downloaded into R2."""


@dataclass(frozen=True)
class CacheResult:
    """Outcome of an ``ensure_cached`` call."""

    r2_key: str
    cache_hit: bool


async def ensure_cached(env: JsProxy, path: str) -> CacheResult:
    """Ensure the file at ``path`` is present in the R2 cache.

    Returns the R2 key the caller should read from. Raises
    :class:`NotFoundError` if the path doesn't resolve in Drive, or
    :class:`DownloadError` if the download/cache write fails.
    """
    # Normalise to an R2 key (lowercase, no leading slash).
    r2_key = path.lower()
    path_segments = [seg for seg in path.split("/") if seg]
    filename = path_segments[-1] if path_segments else "download"

    # ── R2 cache check ───────────────────────────────────────────────
    cached = await env.CACHE.head(r2_key)
    if cached:
        console.log(f"R2 cache hit: {r2_key}")
        return CacheResult(r2_key=r2_key, cache_hit=True)

    console.log(f"R2 cache miss: {r2_key}")

    # ── Resolve Drive file ID (fast-fail on 404) ─────────────────────
    sa_json = str(env.GOOGLE_SERVICE_ACCOUNT)
    token = await get_access_token(sa_json)
    drive_root = str(env.DRIVE_ROOT_ID)

    file_info = await resolve_drive_path(path_segments, drive_root, token)
    if file_info is None:
        raise NotFoundError("File not found in Google Drive")

    file_id: str = str(file_info["id"])
    mime_type: str = str(file_info.get("mimeType") or "application/octet-stream")

    # ── Coordinate via Durable Object ────────────────────────────────
    try:
        async with coordinate(env, r2_key) as session:
            if session.is_downloader:
                await _download_to_r2(
                    env=env,
                    r2_key=r2_key,
                    file_id=file_id,
                    filename=filename,
                    mime_type=mime_type,
                    token=token,
                )
            else:
                console.log(f"Waiting for download: {r2_key}")
                await session.wait()
                console.log(f"Download complete (waiter): {r2_key}")
    except RuntimeError as exc:
        # Waiter saw an error from the downloader.
        console.error(f"Download error (waiter) for {r2_key}: {exc}")
        raise DownloadError(str(exc)) from exc
    except ServeError:
        raise
    except Exception as exc:
        # Downloader's own work failed; error has already been signalled.
        raise DownloadError(str(exc)) from exc

    return CacheResult(r2_key=r2_key, cache_hit=False)


async def _download_to_r2(
    *,
    env: JsProxy,
    r2_key: str,
    file_id: str,
    filename: str,
    mime_type: str,
    token: str,
) -> None:
    """Stream a Drive file into R2 under ``r2_key``."""
    console.log(f"Downloading Drive file {file_id} -> R2 key {r2_key}")
    try:
        drive_resp = await download_drive_file(file_id, token)
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
    except Exception as exc:
        console.error(f"Download failed for {r2_key}: {exc}")
        raise
