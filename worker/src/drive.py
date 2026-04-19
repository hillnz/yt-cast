"""Google Drive API client.

Resolves file paths by walking segments against the Drive API and
downloads files by ID as streaming responses.
"""

from __future__ import annotations

from urllib.parse import quote

from js import JsResponse, console, fetch
from pyodide.ffi import JsProxy

from helpers import to_js


async def resolve_drive_path(
    path_segments: list[str], root_id: str, token: str
) -> JsProxy | None:
    """Walk path segments against the Google Drive API.

    Starting from *root_id*, resolves each segment by querying for a child
    with that name under the current parent.  Returns the final segment's
    file metadata object (id, name, mimeType, size) or ``None`` when any
    segment yields zero results.
    """
    parent_id: str = root_id
    file_info: JsProxy | None = None

    for segment in path_segments:
        # Escape single quotes inside the segment name for the query
        safe_name = segment.replace("\\", "\\\\").replace("'", "\\'")
        query = f"name = '{safe_name}' and '{parent_id}' in parents and trashed = false"
        url = (
            "https://www.googleapis.com/drive/v3/files"
            f"?q={quote(query)}"
            f"&fields=files(id,name,mimeType,size)"
        )

        resp = await fetch(
            url,
            to_js({"headers": {"Authorization": f"Bearer {token}"}}),
        )

        if not resp.ok:
            text = await resp.text()
            status = int(str(resp.status))
            console.error(f"Drive API error ({status}): {text}")
            raise RuntimeError(f"Drive API error ({status}): {text}")

        data: JsProxy = await resp.json()
        files: JsProxy = data.files

        if not files or files.length == 0:
            return None

        file_info = files[0]
        parent_id = str(file_info.id)

    return file_info


async def download_drive_file(file_id: str, token: str) -> JsResponse:
    """Download a file from Google Drive by its ID.

    Returns the raw JS *Response* whose ``.body`` is a ``ReadableStream``
    suitable for piping straight into R2.
    """
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"

    resp = await fetch(
        url,
        to_js({"headers": {"Authorization": f"Bearer {token}"}}),
    )

    if not resp.ok:
        text = await resp.text()
        status = int(str(resp.status))
        console.error(f"Drive download error ({status}): {text}")
        raise RuntimeError(f"Drive download error ({status}): {text}")

    return resp
