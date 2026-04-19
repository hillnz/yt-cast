"""Download router."""

import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from app.dependencies import get_storage, get_ytdl
from app.storage import Storage
from app.ytdl import YtDl

logger = logging.getLogger(__name__)

router = APIRouter(tags=["download"])


class DownloadRequest(BaseModel):
    """Request body for the download endpoint."""

    video_id: str


@router.post("/download", status_code=204)
async def download(
    body: DownloadRequest,
    ytdl: YtDl = Depends(get_ytdl),
    storage: Storage = Depends(get_storage),
) -> Response:
    """Download audio for a video and save to the configured storage backend.

    The request blocks until the download and save complete.
    Returns an empty response on success.
    """
    video_id = body.video_id
    with tempfile.TemporaryDirectory() as tmp_dir:
        output_path = Path(tmp_dir) / f"{video_id}.m4a"
        await ytdl.download_audio(video_id, output_path)
        await storage.save_file(output_path, key=video_id)

    return Response(status_code=204)
