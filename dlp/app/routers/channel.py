"""Channel router."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.dependencies import get_ytdl
from app.ytdl import Channel, Thumbnail, YtDl

router = APIRouter(tags=["channel"])


class ChannelResponse(BaseModel):
    """Channel metadata along with recent video IDs."""

    channel: str
    description: str
    thumbnails: list[Thumbnail]
    webpage_url: str
    epoch: int
    videos: list[str]

    @classmethod
    def from_channel(cls, channel: Channel, videos: list[str]) -> "ChannelResponse":
        """Build a response from a :class:`Channel` and a list of video IDs."""
        return cls(
            channel=channel.channel,
            description=channel.description,
            thumbnails=channel.thumbnails,
            webpage_url=channel.webpage_url,
            epoch=channel.epoch,
            videos=videos,
        )


@router.get("/channel/{channel_id}")
async def get_channel_videos(
    channel_id: str,
    ytdl: YtDl = Depends(get_ytdl),
) -> ChannelResponse:
    """Return channel metadata and recent video IDs for a YouTube channel.

    Accepts a channel name, handle, or ID as *channel_id* and returns the
    channel info together with a ``videos`` field listing recent video IDs
    fetched via yt-dlp.
    """
    channel_info = await ytdl.get_channel_info(channel_id)
    videos = await ytdl.get_channel_videos(channel_info)
    return ChannelResponse.from_channel(channel_info, videos)
