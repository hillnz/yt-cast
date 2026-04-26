"""Orchestrate the per-video download flow.

For each video this module:
  1. Asks the DLP service to archive it (DLP uploads to Drive).
  2. Streams the file from Drive into R2 under ``{feed_id}/{video_id}``.
  3. Deletes the per-video Drive folder so the archive doesn't grow.
"""

from __future__ import annotations

from js import console
from pyodide.ffi import JsProxy

from dlp import DlpClient
from drive import (
    delete_drive_file,
    download_drive_file,
    list_drive_children,
    resolve_drive_path,
)
from google_auth import get_access_token
from helpers import to_js
from ytcast_shared import video_path

# Custom-metadata key used to store the SponsorBlock segment hash on R2
# objects, so a later run can tell whether the segments have changed.
SEGMENT_HASH_METADATA_KEY = "segmentHash"


class VideoDownloadError(Exception):
    """Raised when a video could not be archived through DLP + Drive."""


async def head_video(env: JsProxy, feed_id: str, video_id: str) -> JsProxy | None:
    """Return the R2 head object for the cached audio, or ``None``."""
    head = await env.STORAGE.head(video_path(feed_id, video_id))
    return head if head else None


async def list_cached_video_ids(env: JsProxy, feed_id: str) -> set[str]:
    """Return the set of video IDs already present in R2 for *feed_id*.

    Reads the ``{feed_id}/`` listing and strips out keys that aren't
    per-video objects (notably ``feed.xml``). Used so a partial feed can
    include audio that's already cached even before SponsorBlock /
    metadata checks have been run for the current message.
    """
    prefix = f"{feed_id}/"
    cached: set[str] = set()
    cursor: str | None = None
    while True:
        opts: dict[str, object] = {"prefix": prefix, "limit": 1000}
        if cursor is not None:
            opts["cursor"] = cursor
        result = await env.STORAGE.list(to_js(opts))
        objects = getattr(result, "objects", None) or []
        for obj in objects:
            key = str(obj.key)
            if not key.startswith(prefix):
                continue
            suffix = key[len(prefix):]
            if not suffix or "/" in suffix or suffix == "feed.xml":
                continue
            cached.add(suffix)
        if not bool(getattr(result, "truncated", False)):
            break
        next_cursor = getattr(result, "cursor", None)
        cursor = str(next_cursor) if next_cursor else None
        if cursor is None:
            break
    return cached


def existing_segment_hash(head: JsProxy | None) -> str | None:
    """Return the segment hash stored on an R2 head object, if any."""
    if head is None:
        return None
    custom = getattr(head, "customMetadata", None)
    if custom is None:
        return None
    value = getattr(custom, SEGMENT_HASH_METADATA_KEY, None)
    if value is None:
        return None
    text = str(value)
    return text or None


async def download_video(
    env: JsProxy,
    *,
    dlp: DlpClient,
    feed_id: str,
    video_id: str,
    segment_hash: str,
) -> None:
    """Download *video_id* through DLP, copy to R2, clean up Drive."""
    console.log(f"Archiving video via DLP: {video_id}")
    await dlp.download_video(video_id)

    token = await get_access_token(str(env.GOOGLE_SERVICE_ACCOUNT))
    drive_root = str(env.DRIVE_ROOT_ID)

    folder = await resolve_drive_path([video_id], drive_root, token)
    if folder is None:
        raise VideoDownloadError(f"Drive folder missing after DLP download: {video_id}")

    folder_id = str(folder["id"])
    children = await list_drive_children(folder_id, token)
    files = [
        c
        for c in children
        if str(c.get("mimeType", "")) != "application/vnd.google-apps.folder"
    ]
    if not files:
        raise VideoDownloadError(
            f"Drive folder empty after DLP download: {video_id}"
        )

    # DLP uploads exactly one audio file per video — take the first.
    file_info = files[0]
    file_id = str(file_info["id"])
    mime_type = str(file_info.get("mimeType") or "audio/mp4")
    filename = str(file_info.get("name") or f"{video_id}.m4a")

    drive_resp = await download_drive_file(file_id, token)
    await env.STORAGE.put(
        video_path(feed_id, video_id),
        drive_resp.body,
        to_js(
            {
                "httpMetadata": to_js({"contentType": mime_type}),
                "customMetadata": to_js(
                    {
                        "filename": filename,
                        "videoId": video_id,
                        SEGMENT_HASH_METADATA_KEY: segment_hash,
                    }
                ),
            }
        ),
    )
    console.log(f"R2 write complete: {video_path(feed_id, video_id)}")

    await delete_drive_file(folder_id, token)
    console.log(f"Drive folder deleted: {video_id}")
