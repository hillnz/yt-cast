"""Tests for the podcast feed item module."""

from __future__ import annotations

from xml.etree.ElementTree import Element, tostring

from feed.item import _format_upload_date, _parse_duration_seconds, video_to_item

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ITUNES_NS = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"


def _find(element: Element, tag: str) -> Element | None:
    """Find a direct child by tag, returning None if missing."""
    return element.find(tag)


def _text(element: Element, tag: str) -> str | None:
    """Return the text of a direct child, or None."""
    child = _find(element, tag)
    return child.text if child is not None and child.text is not None else None


def _attr(element: Element, tag: str, attr: str) -> str | None:
    """Return an attribute of a direct child element."""
    child = _find(element, tag)
    return child.get(attr) if child is not None else None


# ---------------------------------------------------------------------------
# Sample video data
# ---------------------------------------------------------------------------

SAMPLE_VIDEO = {
    "id": "dQw4w9WgXcQ",
    "title": "Rick Astley - Never Gonna Give You Up",
    "description": "The official video for “Never Gonna Give You Up” by Rick Astley.",
    "upload_date": "20091025",
    "duration": "03:33",
}


# ---------------------------------------------------------------------------
# _parse_duration_seconds
# ---------------------------------------------------------------------------


class TestParseDurationSeconds:
    def test_hhmmss(self) -> None:
        assert _parse_duration_seconds("01:23:45") == 5025

    def test_mmss(self) -> None:
        assert _parse_duration_seconds("03:33") == 213

    def test_integer_string(self) -> None:
        assert _parse_duration_seconds("213") == 213

    def test_empty(self) -> None:
        assert _parse_duration_seconds("") == 0

    def test_garbage(self) -> None:
        assert _parse_duration_seconds("not-a-duration") == 0

    def test_single_number(self) -> None:
        assert _parse_duration_seconds("45") == 45

    def test_zero(self) -> None:
        assert _parse_duration_seconds("0") == 0

    def test_hhmmss_with_large_hours(self) -> None:
        assert _parse_duration_seconds("12:00:00") == 43200


# ---------------------------------------------------------------------------
# _format_upload_date
# ---------------------------------------------------------------------------


class TestFormatUploadDate:
    def test_yyyymmdd(self) -> None:
        result = _format_upload_date("20091025")
        assert result == "Sun, 25 Oct 2009 00:00:00 +0000"

    def test_empty(self) -> None:
        assert _format_upload_date("") is None

    def test_too_short(self) -> None:
        assert _format_upload_date("2009") is None

    def test_invalid_month(self) -> None:
        assert _format_upload_date("20091301") is None

    def test_none_like(self) -> None:
        assert _format_upload_date("00000000") is None


# ---------------------------------------------------------------------------
# video_to_item
# ---------------------------------------------------------------------------


class TestVideoToItem:
    def test_returns_element(self) -> None:
        item = video_to_item(SAMPLE_VIDEO, "https://cdn.example.com/audio.mp3")
        assert isinstance(item, Element)
        assert item.tag == "item"

    def test_title(self) -> None:
        item = video_to_item(SAMPLE_VIDEO, "https://cdn.example.com/audio.mp3")
        assert _text(item, "title") == "Rick Astley - Never Gonna Give You Up"

    def test_link(self) -> None:
        item = video_to_item(SAMPLE_VIDEO, "https://cdn.example.com/audio.mp3")
        assert _text(item, "link") == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    def test_description(self) -> None:
        item = video_to_item(SAMPLE_VIDEO, "https://cdn.example.com/audio.mp3")
        assert _text(item, "description") == SAMPLE_VIDEO["description"]

    def test_guid(self) -> None:
        item = video_to_item(SAMPLE_VIDEO, "https://cdn.example.com/audio.mp3")
        assert _text(item, "guid") == "yt:dQw4w9WgXcQ"
        assert _attr(item, "guid", "isPermaLink") == "false"

    def test_pub_date(self) -> None:
        item = video_to_item(SAMPLE_VIDEO, "https://cdn.example.com/audio.mp3")
        assert _text(item, "pubDate") == "Sun, 25 Oct 2009 00:00:00 +0000"

    def test_enclosure_url(self) -> None:
        item = video_to_item(SAMPLE_VIDEO, "https://cdn.example.com/audio.mp3")
        assert _attr(item, "enclosure", "url") == "https://cdn.example.com/audio.mp3"

    def test_enclosure_default_mime_type(self) -> None:
        item = video_to_item(SAMPLE_VIDEO, "https://cdn.example.com/audio.mp3")
        assert _attr(item, "enclosure", "type") == "audio/mpeg"

    def test_enclosure_custom_mime_type(self) -> None:
        item = video_to_item(
            SAMPLE_VIDEO,
            "https://cdn.example.com/audio.m4a",
            mime_type="audio/mp4",
        )
        assert _attr(item, "enclosure", "type") == "audio/mp4"

    def test_enclosure_length_is_zero(self) -> None:
        """Length is required by RSS spec but unavailable from the API."""
        item = video_to_item(SAMPLE_VIDEO, "https://cdn.example.com/audio.mp3")
        assert _attr(item, "enclosure", "length") == "0"

    def test_itunes_duration(self) -> None:
        item = video_to_item(SAMPLE_VIDEO, "https://cdn.example.com/audio.mp3")
        itunes_dur = _find(item, f"{ITUNES_NS}duration")
        assert itunes_dur is not None
        assert itunes_dur.text == "03:33"

    def test_itunes_summary(self) -> None:
        item = video_to_item(SAMPLE_VIDEO, "https://cdn.example.com/audio.mp3")
        itunes_summary = _find(item, f"{ITUNES_NS}summary")
        assert itunes_summary is not None
        assert itunes_summary.text == SAMPLE_VIDEO["description"]

    def test_itunes_episode_type(self) -> None:
        item = video_to_item(SAMPLE_VIDEO, "https://cdn.example.com/audio.mp3")
        itunes_type = _find(item, f"{ITUNES_NS}episodeType")
        assert itunes_type is not None
        assert itunes_type.text == "full"

    def test_audio_url_is_configurable(self) -> None:
        custom_url = "https://r2.example.com/bucket/videos/dQw4w9WgXcQ.m4a"
        item = video_to_item(SAMPLE_VIDEO, custom_url, mime_type="audio/mp4")
        assert _attr(item, "enclosure", "url") == custom_url
        assert _attr(item, "enclosure", "type") == "audio/mp4"

    def test_missing_upload_date_omits_pub_date(self) -> None:
        video = {**SAMPLE_VIDEO, "upload_date": ""}
        item = video_to_item(video, "https://cdn.example.com/audio.mp3")
        assert _find(item, "pubDate") is None

    def test_invalid_upload_date_omits_pub_date(self) -> None:
        video = {**SAMPLE_VIDEO, "upload_date": "not-a-date"}
        item = video_to_item(video, "https://cdn.example.com/audio.mp3")
        assert _find(item, "pubDate") is None

    def test_empty_duration_defaults_to_zero(self) -> None:
        video = {**SAMPLE_VIDEO, "duration": ""}
        item = video_to_item(video, "https://cdn.example.com/audio.mp3")
        itunes_dur = _find(item, f"{ITUNES_NS}duration")
        assert itunes_dur is not None
        assert itunes_dur.text == "0"

    def test_empty_video_fields(self) -> None:
        """Gracefully handles a video dict with all-empty fields."""
        video = {
            "id": "",
            "title": "",
            "description": "",
            "upload_date": "",
            "duration": "",
        }
        item = video_to_item(video, "https://cdn.example.com/audio.mp3")
        assert _text(item, "title") == ""
        assert _text(item, "link") == "https://www.youtube.com/watch?v="
        assert _text(item, "description") == ""
        assert _text(item, "guid") == "yt:"
        assert _find(item, "pubDate") is None

    def test_serialisable_to_xml(self) -> None:
        """The returned Element should produce valid XML when serialised."""
        item = video_to_item(SAMPLE_VIDEO, "https://cdn.example.com/audio.mp3")
        xml_bytes = tostring(item, encoding="unicode")
        # tostring may add namespace declarations on the root element,
        # so match a namespaced <item> tag too.
        assert "<item" in xml_bytes
        assert "</item>" in xml_bytes
        assert "dQw4w9WgXcQ" in xml_bytes
        assert "https://cdn.example.com/audio.mp3" in xml_bytes

    def test_integer_duration_passthrough(self) -> None:
        """Some yt-dlp versions return duration as an integer string."""
        video = {**SAMPLE_VIDEO, "duration": "213"}
        item = video_to_item(video, "https://cdn.example.com/audio.mp3")
        itunes_dur = _find(item, f"{ITUNES_NS}duration")
        assert itunes_dur is not None
        assert itunes_dur.text == "213"
