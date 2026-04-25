"""Orchestrate the per-video download flow.

For each video this module:
  1. Asks the DLP service to archive it (DLP uploads to Drive).
  2. Streams the file from Drive into R2 under ``{bucket}/{feed_id}/{video_id}``,
     where *bucket* is the lifecycle prefix that controls retention.
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


class VideoDownloadError(Exception):
    """Raised when a video could not be archived through DLP + Drive."""


async def video_exists(
    env: JsProxy, feed_id: str, video_id: str, bucket: str
) -> bool:
    """Return True if R2 already has the audio under *bucket*."""
    head = await env.STORAGE.head(video_path(feed_id, video_id, bucket))
    return head is not None


async def download_video(
    env: JsProxy,
    *,
    dlp: DlpClient,
    feed_id: str,
    video_id: str,
    bucket: str,
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
        video_path(feed_id, video_id, bucket),
        drive_resp.body,
        to_js(
            {
                "httpMetadata": to_js({"contentType": mime_type}),
                "customMetadata": to_js(
                    {"filename": filename, "videoId": video_id}
                ),
            }
        ),
    )
    console.log(f"R2 write complete: {video_path(feed_id, video_id, bucket)}")

    await delete_drive_file(folder_id, token)
    console.log(f"Drive folder deleted: {video_id}")
