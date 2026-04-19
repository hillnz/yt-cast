"""Channel router."""

from fastapi import APIRouter, Depends

from app.dependencies import get_ytdl
from app.ytdl import YtDl

router = APIRouter(tags=["channel"])


@router.get("/channel/{channel_id}")
async def get_channel_videos(
    channel_id: str,
    ytdl: YtDl = Depends(get_ytdl),
) -> list[str]:
    """Return a list of recent video IDs for a YouTube channel.

    Accepts a channel name, handle, or ID as *channel_id* and returns
    video IDs fetched via yt-dlp.
    """
    channel_info = await ytdl.get_channel_info(channel_id)
    return await ytdl.get_channel_videos(channel_info)
