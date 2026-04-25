"""Build a podcast RSS feed for a channel.

Pure assembly: takes a channel descriptor and the per-video metadata
that has already been fetched, and emits a serialised RSS document
with one ``<item>`` per video. I/O lives elsewhere.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable
from xml.etree.ElementTree import Element, tostring

from feed import channel_to_feed, video_to_item
from feed.channel import ChannelData, YTCAST_NS
from feed.item import VideoData

_ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
_ATOM_NS = "http://www.w3.org/2005/Atom"

_AUDIO_MIME_TYPE = "audio/mp4"


def build_feed(
    *,
    channel: ChannelData,
    channel_id: str,
    videos: list[VideoData],
    audio_url_for: Callable[[str], str],
    last_built: datetime,
    feed_url: str = "",
) -> bytes:
    """Render a podcast RSS document as UTF-8 bytes."""
    channel_element = channel_to_feed(
        channel,
        channel_id=channel_id,
        last_built=last_built,
        feed_url=feed_url,
    )
    for video in videos:
        channel_element.append(
            video_to_item(
                video,
                audio_url_for(video["id"]),
                mime_type=_AUDIO_MIME_TYPE,
            )
        )

    rss = Element(
        "rss",
        attrib={
            "version": "2.0",
            "xmlns:itunes": _ITUNES_NS,
            "xmlns:atom": _ATOM_NS,
            "xmlns:ytcast": YTCAST_NS,
        },
    )
    rss.append(channel_element)

    return tostring(
        rss,
        encoding="utf-8",
        xml_declaration=True,
        short_empty_elements=True,
    )
