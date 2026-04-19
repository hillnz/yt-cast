"""Video router."""

from fastapi import APIRouter, Depends

from app.dependencies import get_ytdl
from app.ytdl import Video, YtDl

router = APIRouter(tags=["video"])


@router.get("/video/{video_id}", response_model=Video)
async def get_video(
    video_id: str,
    ytdl: YtDl = Depends(get_ytdl),
) -> Video:
    """Return metadata for a single YouTube video.

    Fetches video info via yt-dlp and returns a :class:`Video` object.
    """
    return await ytdl.get_video_info(video_id)
