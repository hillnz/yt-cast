"""Convert DLP Video API responses into podcast RSS feed items."""

from __future__ import annotations

from typing import TypedDict
from xml.etree.ElementTree import Element, SubElement


class VideoData(TypedDict):
    """Shape of the DLP API ``/video/{video_id}`` response.

    Matches the ``Video`` Pydantic model in the DLP archive service.
    """

    id: str
    title: str
    description: str
    upload_date: str
    duration: str


# Default values for enclosure when the source video data lacks them.
_DEFAULT_MIME_TYPE = "audio/mpeg"
_DEFAULT_DURATION_SECONDS = 0


def _parse_duration_seconds(duration: str) -> int:
    """Parse an ``HH:MM:SS`` or ``MM:SS`` or integer string into seconds.

    The DLP API ``duration`` field comes from yt-dlp's
    ``duration_string``, which is typically ``"HH:MM:SS"`` or
    ``"MM:SS"`` for shorter videos.  Falls back to ``0`` on any parse
    error.
    """
    if not duration:
        return _DEFAULT_DURATION_SECONDS

    try:
        return int(duration)
    except ValueError:
        pass

    parts = duration.split(":")
    try:
        if len(parts) == 3:
            h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
            return h * 3600 + m * 60 + s
        if len(parts) == 2:
            m, s = int(parts[0]), int(parts[1])
            return m * 60 + s
    except (ValueError, IndexError):
        pass

    return _DEFAULT_DURATION_SECONDS


def _format_upload_date(upload_date: str) -> str | None:
    """Convert ``YYYYMMDD`` date string to RFC 822 format for RSS.

    Returns ``None`` if *upload_date* is empty or unparseable.
    """
    if not upload_date or len(upload_date) < 8:
        return None

    try:
        from datetime import datetime

        dt = datetime.strptime(upload_date[:8], "%Y%m%d")
    except ValueError:
        return None

    # RFC 822 format used in RSS <pubDate>
    return dt.strftime("%a, %d %b %Y 00:00:00 +0000")


def video_to_item(
    video: VideoData,
    audio_url: str,
    *,
    mime_type: str = _DEFAULT_MIME_TYPE,
) -> Element:
    """Convert a DLP ``/video/{video_id}`` response into an RSS ``<item>``.

    Parameters
    ----------
    video:
        A dict matching the DLP API ``Video`` model, with keys
        ``id``, ``title``, ``description``, ``upload_date``, and
        ``duration``.
    audio_url:
        Full URL to the audio enclosure (e.g. an R2 or CDN URL).
        Podcast clients will use this to download the episode audio.
    mime_type:
        MIME type of the audio enclosure.  Defaults to
        ``"audio/mpeg"`` (for ``.mp3``).  Use ``"audio/mp4"`` for
        ``.m4a`` / AAC audio, or ``"audio/ogg"`` for Ogg Vorbis.

    Returns
    -------
    Element
        An ``xml.etree.ElementTree.Element`` representing the RSS
        ``<item>``.  The caller can append this to an RSS ``<channel>``
        element and serialise the full document with
        :func:`~xml.etree.ElementTree.tostring`.
    """
    video_id = video.get("id", "")
    title = video.get("title", "")
    description = video.get("description", "")
    upload_date = video.get("upload_date", "")
    duration = video.get("duration", "")

    item = Element("item")

    SubElement(item, "title").text = title
    SubElement(item, "link").text = f"https://www.youtube.com/watch?v={video_id}"
    SubElement(item, "description").text = description

    # GUID — uses the YouTube watch URL so aggregators can deduplicate.
    guid = SubElement(item, "guid")
    guid.text = f"yt:{video_id}"
    guid.set("isPermaLink", "false")

    # Publication date
    pub_date_str = _format_upload_date(upload_date)
    if pub_date_str is not None:
        SubElement(item, "pubDate").text = pub_date_str

    # Audio enclosure — the critical piece for podcast clients.
    SubElement(
        item,
        "enclosure",
        attrib={
            "url": audio_url,
            "type": mime_type,
            # Length is required by the RSS spec but we don't have the
            # actual file size from the API; use 0 as a placeholder.
            "length": "0",
        },
    )

    # iTunes podcast namespace extensions (widely used by podcast
    # clients for duration, episode type, etc.).
    itunes_duration = SubElement(
        item, "{http://www.itunes.com/dtds/podcast-1.0.dtd}duration"
    )
    itunes_duration.text = duration or "0"

    SubElement(
        item, "{http://www.itunes.com/dtds/podcast-1.0.dtd}summary"
    ).text = description

    SubElement(
        item, "{http://www.itunes.com/dtds/podcast-1.0.dtd}episodeType"
    ).text = "full"

    return item
