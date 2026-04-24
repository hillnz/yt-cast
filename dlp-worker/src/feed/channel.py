"""Convert DLP Channel API responses into podcast RSS feed channels."""

from __future__ import annotations

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


def _pick_best_thumbnail(thumbnails: list[ThumbnailData]) -> str | None:
    """Return the URL of the largest thumbnail, or ``None`` if empty.

    Podcast clients prefer high-resolution artwork, so we pick the
    thumbnail with the greatest area (width × height).  Falls back to
    the last thumbnail in the list (yt-dlp typically orders them
    ascending by size) or ``None`` when the list is empty.
    """
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

    # If all thumbnails lacked dimensions (best never updated), fall back
    # to the last one (yt-dlp typically orders them ascending by size).
    if best is None:
        best = thumbnails[-1]

    return best.get("url") or None


def _format_epoch_rfc822(epoch: int) -> str | None:
    """Convert a Unix epoch timestamp to RFC 822 format for RSS.

    Returns ``None`` if *epoch* is ``0`` or unparseable.
    """
    if not epoch:
        return None

    try:
        from datetime import datetime, timezone

        dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
    except (ValueError, OSError):
        return None

    return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")


def channel_to_feed(
    channel: ChannelData,
    *,
    feed_url: str = "",
) -> Element:
    """Convert a DLP ``/channel/{channel_id}`` response into an RSS
    ``<channel>`` element (without ``<item>`` entries).

    Parameters
    ----------
    channel:
        A dict matching the DLP API ``ChannelResponse`` model, with
        keys ``channel``, ``description``, ``thumbnails``,
        ``webpage_url``, ``epoch``, and ``videos``.
    feed_url:
        The canonical URL of this podcast feed itself.  Populates the
        ``<atom:link rel="self">`` element so aggregators can find the
        feed source.  Optional; if empty the element is omitted.
    audio_mime_type:
        MIME type for episodes in this feed.  Defaults to
        ``"audio/mpeg"`` (MP3).  Written to the iTunes ``<type>`` and
        ``<format>`` elements so podcast directories categorise the
        feed correctly.

    Returns
    -------
    Element
        An ``xml.etree.ElementTree.Element`` representing the RSS
        ``<channel>``.  The caller can append ``<item>`` elements and
        then wrap everything in an ``<rss>`` root element before
        serialising with :func:`~xml.etree.ElementTree.tostring`.
    """
    name = channel.get("channel", "")
    description = channel.get("description", "")
    thumbnails = channel.get("thumbnails", [])
    webpage_url = channel.get("webpage_url", "")
    epoch = channel.get("epoch", 0)

    ch = Element("channel")

    SubElement(ch, "title").text = name
    SubElement(ch, "link").text = webpage_url
    SubElement(ch, "description").text = description

    # Language — YouTube channels don't expose language metadata from
    # the DLP API, so we omit it rather than guess.

    # Last-build date from the DLP epoch timestamp.
    last_build = _format_epoch_rfc822(epoch)
    if last_build is not None:
        SubElement(ch, "lastBuildDate").text = last_build

    # Atom self-link for aggregators.
    if feed_url:
        atom_link = SubElement(
            ch,
            "{http://www.w3.org/2005/Atom}link",
        )
        atom_link.set("href", feed_url)
        atom_link.set("rel", "self")
        atom_link.set("type", "application/rss+xml")

    # iTunes podcast extension elements.
    SubElement(ch, f"{{{_ITUNES_NS}}}author").text = name

    itunes_summary = SubElement(ch, f"{{{_ITUNES_NS}}}summary")
    itunes_summary.text = description

    SubElement(ch, f"{{{_ITUNES_NS}}}explicit").text = "false"

    itunes_owner = SubElement(ch, f"{{{_ITUNES_NS}}}owner")
    SubElement(itunes_owner, f"{{{_ITUNES_NS}}}name").text = name

    # iTunes image — use the best-quality thumbnail as podcast artwork.
    thumb_url = _pick_best_thumbnail(thumbnails)
    if thumb_url is not None:
        SubElement(ch, f"{{{_ITUNES_NS}}}image").set("href", thumb_url)

    # iTunes category — default to a generic "Arts" category since
    # the DLP API doesn't expose channel categories.
    itunes_cat = SubElement(ch, f"{{{_ITUNES_NS}}}category")
    itunes_cat.set("text", "Arts")

    return ch
