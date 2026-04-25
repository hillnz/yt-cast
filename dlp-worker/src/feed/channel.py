"""Convert DLP Channel API responses into podcast RSS feed channels."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TypedDict
from xml.etree.ElementTree import Element, SubElement


class ThumbnailData(TypedDict):
    """Shape of a single thumbnail from the DLP API."""

    url: str
    width: int | None
    height: int | None


class ChannelData(TypedDict):
    """Shape of the DLP API ``/channel/{channel_id}`` response.

    Matches the ``ChannelResponse`` Pydantic model in the DLP archive
    service.
    """

    channel: str
    description: str
    thumbnails: list[ThumbnailData]
    webpage_url: str
    epoch: int
    videos: list[str]


# iTunes podcast namespace URI used for Apple Podcasts extensions.
_ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
# Custom yt-cast namespace for fields we round-trip through the feed.
YTCAST_NS = "https://yt-cast.invalid/ns"


def _pick_best_thumbnail(thumbnails: list[ThumbnailData]) -> str | None:
    """Return the URL of the largest thumbnail, or ``None`` if empty."""
    if not thumbnails:
        return None

    best: ThumbnailData | None = None
    best_area: int = 0

    for thumb in thumbnails:
        w = thumb.get("width") or 0
        h = thumb.get("height") or 0
        area = w * h
        if area > best_area:
            best_area = area
            best = thumb

    if best is None:
        best = thumbnails[-1]

    return best.get("url") or None


def _format_rfc822(dt: datetime) -> str:
    """Format a datetime as RFC 822 in UTC."""
    return dt.astimezone(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")


def channel_to_feed(
    channel: ChannelData,
    *,
    channel_id: str,
    last_built: datetime,
    feed_url: str = "",
) -> Element:
    """Convert a DLP ``/channel/{channel_id}`` response into an RSS
    ``<channel>`` element (without ``<item>`` entries).

    Parameters
    ----------
    channel:
        Channel metadata from the DLP API.
    channel_id:
        The original channel handle/ID supplied by the user. Stored in a
        custom ``<ytcast:channelId>`` element so it can be recovered
        from a parsed feed without keeping a side table.
    last_built:
        Timestamp this feed build represents. Written to ``<lastBuildDate>``
        and used by the consumer to throttle rebuilds.
    feed_url:
        Canonical URL of this feed (Atom self-link).
    """
    name = channel.get("channel", "")
    description = channel.get("description", "")
    thumbnails = channel.get("thumbnails", [])
    webpage_url = channel.get("webpage_url", "")

    ch = Element("channel")

    SubElement(ch, "title").text = name
    SubElement(ch, "link").text = webpage_url
    SubElement(ch, "description").text = description
    SubElement(ch, "lastBuildDate").text = _format_rfc822(last_built)

    SubElement(ch, f"{{{YTCAST_NS}}}channelId").text = channel_id

    if feed_url:
        atom_link = SubElement(ch, "{http://www.w3.org/2005/Atom}link")
        atom_link.set("href", feed_url)
        atom_link.set("rel", "self")
        atom_link.set("type", "application/rss+xml")

    SubElement(ch, f"{{{_ITUNES_NS}}}author").text = name
    SubElement(ch, f"{{{_ITUNES_NS}}}summary").text = description
    SubElement(ch, f"{{{_ITUNES_NS}}}explicit").text = "false"

    itunes_owner = SubElement(ch, f"{{{_ITUNES_NS}}}owner")
    SubElement(itunes_owner, f"{{{_ITUNES_NS}}}name").text = name

    thumb_url = _pick_best_thumbnail(thumbnails)
    if thumb_url is not None:
        SubElement(ch, f"{{{_ITUNES_NS}}}image").set("href", thumb_url)

    itunes_cat = SubElement(ch, f"{{{_ITUNES_NS}}}category")
    itunes_cat.set("text", "Arts")

    return ch
