"""Google Drive API client.

Resolves file paths by walking segments against the Drive API and
downloads files by ID as streaming responses.
"""

from __future__ import annotations

from typing import Any

import httpx
from workers import FetchResponse, fetch


async def resolve_drive_path(
    path_segments: list[str], root_id: str, token: str
) -> dict[str, Any] | None:
    """Walk path segments against the Google Drive API.

    Starting from *root_id*, resolves each segment by querying for a child
    with that name under the current parent.  Returns the final segment's
    file metadata dict (id, name, mimeType, size) or ``None`` when any
    segment yields zero results.
    """
    parent_id: str = root_id
    file_info: dict[str, Any] | None = None

    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(
        base_url="https://www.googleapis.com",
        headers=headers,
        timeout=30.0,
    ) as client:
        for segment in path_segments:
            # Escape single quotes inside the segment name for the query
            safe_name = segment.replace("\\", "\\\\").replace("'", "\\'")
            query = (
                f"name = '{safe_name}' and '{parent_id}' in parents and trashed = false"
            )

            resp = await client.get(
                "/drive/v3/files",
                params={
                    "q": query,
                    "fields": "files(id,name,mimeType,size)",
                },
            )

            if resp.status_code != httpx.codes.OK:
                raise RuntimeError(f"Drive API error ({resp.status_code}): {resp.text}")

            data = resp.json()
            files: list[dict[str, Any]] = data.get("files") or []

            if not files:
                return None

            file_info = files[0]
            parent_id = str(file_info["id"])

    return file_info


async def download_drive_file(file_id: str, token: str) -> FetchResponse:
    """Download a file from Google Drive by its ID.

    Returns the workers ``FetchResponse`` whose ``.body`` is a JS
    ``ReadableStream`` suitable for piping straight into R2.
    """
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"

    resp = await fetch(url, headers={"Authorization": f"Bearer {token}"})

    if not resp.ok:
        text = await resp.text()
        raise RuntimeError(f"Drive download error ({resp.status}): {text}")

    return resp
