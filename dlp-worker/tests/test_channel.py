"""Tests for the podcast feed channel module."""

from __future__ import annotations

from xml.etree.ElementTree import Element, tostring

from feed.channel import (
    _format_epoch_rfc822,
    _pick_best_thumbnail,
    channel_to_feed,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ITUNES_NS = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"
ATOM_NS = "{http://www.w3.org/2005/Atom}"


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
# Sample channel data
# ---------------------------------------------------------------------------

SAMPLE_THUMBNAILS = [
    {"url": "https://i.ytimg.com/vi/dQ/thumb1.jpg", "width": 120, "height": 90},
    {"url": "https://i.ytimg.com/vi/dQ/thumb2.jpg", "width": 320, "height": 180},
    {"url": "https://i.ytimg.com/vi/dQ/thumb3.jpg", "width": 640, "height": 480},
]

SAMPLE_CHANNEL = {
    "channel": "Rick Astley",
    "description": "Official YouTube channel of Rick Astley.",
    "thumbnails": SAMPLE_THUMBNAILS,
    "webpage_url": "https://www.youtube.com/@RickAstleyYT",
    "epoch": 1720000000,
    "videos": ["dQw4w9WgXcQ", "abc123def45"],
}


# ---------------------------------------------------------------------------
# _pick_best_thumbnail
# ---------------------------------------------------------------------------


class TestPickBestThumbnail:
    def test_picks_largest_area(self) -> None:
        result = _pick_best_thumbnail(SAMPLE_THUMBNAILS)
        assert result == "https://i.ytimg.com/vi/dQ/thumb3.jpg"

    def test_empty_list(self) -> None:
        assert _pick_best_thumbnail([]) is None

    def test_single_thumbnail(self) -> None:
        thumbs = [{"url": "https://example.com/img.jpg", "width": 100, "height": 100}]
        assert _pick_best_thumbnail(thumbs) == "https://example.com/img.jpg"

    def test_no_dimensions_falls_back_to_last(self) -> None:
        thumbs = [
            {"url": "https://example.com/small.jpg", "width": None, "height": None},
            {"url": "https://example.com/big.jpg", "width": None, "height": None},
        ]
        assert _pick_best_thumbnail(thumbs) == "https://example.com/big.jpg"

    def test_missing_url_returns_none(self) -> None:
        thumbs = [{"url": "", "width": 100, "height": 100}]
        assert _pick_best_thumbnail(thumbs) is None

    def test_mixed_dimensions(self) -> None:
        thumbs = [
            {"url": "https://example.com/a.jpg", "width": 100, "height": 100},
            {"url": "https://example.com/b.jpg", "width": None, "height": None},
            {"url": "https://example.com/c.jpg", "width": 200, "height": 200},
        ]
        assert _pick_best_thumbnail(thumbs) == "https://example.com/c.jpg"


# ---------------------------------------------------------------------------
# _format_epoch_rfc822
# ---------------------------------------------------------------------------


class TestFormatEpochRfc822:
    def test_valid_epoch(self) -> None:
        result = _format_epoch_rfc822(1720000000)
        assert result == "Wed, 03 Jul 2024 09:46:40 +0000"

    def test_zero_epoch(self) -> None:
        assert _format_epoch_rfc822(0) is None

    def test_negative_epoch(self) -> None:
        # Negative epoch values represent dates before 1970; should still parse.
        result = _format_epoch_rfc822(-1)
        assert result is not None
        assert "1969" in result

    def test_reasonably_large_epoch(self) -> None:
        result = _format_epoch_rfc822(1700000000)
        assert result is not None
        assert "2023" in result


# ---------------------------------------------------------------------------
# channel_to_feed
# ---------------------------------------------------------------------------


class TestChannelToFeed:
    def test_returns_element(self) -> None:
        ch = channel_to_feed(SAMPLE_CHANNEL)
        assert isinstance(ch, Element)
        assert ch.tag == "channel"

    def test_title(self) -> None:
        ch = channel_to_feed(SAMPLE_CHANNEL)
        assert _text(ch, "title") == "Rick Astley"

    def test_link(self) -> None:
        ch = channel_to_feed(SAMPLE_CHANNEL)
        assert _text(ch, "link") == "https://www.youtube.com/@RickAstleyYT"

    def test_description(self) -> None:
        ch = channel_to_feed(SAMPLE_CHANNEL)
        assert _text(ch, "description") == "Official YouTube channel of Rick Astley."

    def test_last_build_date(self) -> None:
        ch = channel_to_feed(SAMPLE_CHANNEL)
        assert _text(ch, "lastBuildDate") == "Wed, 03 Jul 2024 09:46:40 +0000"

    def test_no_items(self) -> None:
        """The feed channel should NOT contain any <item> elements."""
        ch = channel_to_feed(SAMPLE_CHANNEL)
        assert ch.find("item") is None

    def test_itunes_author(self) -> None:
        ch = channel_to_feed(SAMPLE_CHANNEL)
        assert _text(ch, f"{ITUNES_NS}author") == "Rick Astley"

    def test_itunes_summary(self) -> None:
        ch = channel_to_feed(SAMPLE_CHANNEL)
        assert (
            _text(ch, f"{ITUNES_NS}summary")
            == "Official YouTube channel of Rick Astley."
        )

    def test_itunes_explicit(self) -> None:
        ch = channel_to_feed(SAMPLE_CHANNEL)
        assert _text(ch, f"{ITUNES_NS}explicit") == "false"

    def test_itunes_owner_name(self) -> None:
        ch = channel_to_feed(SAMPLE_CHANNEL)
        owner = _find(ch, f"{ITUNES_NS}owner")
        assert owner is not None
        name = owner.find(f"{ITUNES_NS}name")
        assert name is not None
        assert name.text == "Rick Astley"

    def test_itunes_image(self) -> None:
        ch = channel_to_feed(SAMPLE_CHANNEL)
        img = _find(ch, f"{ITUNES_NS}image")
        assert img is not None
        assert img.get("href") == "https://i.ytimg.com/vi/dQ/thumb3.jpg"

    def test_itunes_category(self) -> None:
        ch = channel_to_feed(SAMPLE_CHANNEL)
        cat = _find(ch, f"{ITUNES_NS}category")
        assert cat is not None
        assert cat.get("text") == "Arts"

    def test_atom_self_link(self) -> None:
        ch = channel_to_feed(SAMPLE_CHANNEL, feed_url="https://example.com/feed.xml")
        atom_link = _find(ch, f"{ATOM_NS}link")
        assert atom_link is not None
        assert atom_link.get("href") == "https://example.com/feed.xml"
        assert atom_link.get("rel") == "self"
        assert atom_link.get("type") == "application/rss+xml"

    def test_no_atom_link_when_feed_url_empty(self) -> None:
        ch = channel_to_feed(SAMPLE_CHANNEL)
        atom_link = _find(ch, f"{ATOM_NS}link")
        assert atom_link is None

    def test_no_atom_link_when_feed_url_not_provided(self) -> None:
        ch = channel_to_feed(SAMPLE_CHANNEL)
        atom_link = _find(ch, f"{ATOM_NS}link")
        assert atom_link is None

    def test_zero_epoch_omits_last_build_date(self) -> None:
        channel = {**SAMPLE_CHANNEL, "epoch": 0}
        ch = channel_to_feed(channel)
        assert _find(ch, "lastBuildDate") is None

    def test_no_thumbnails_omits_itunes_image(self) -> None:
        channel = {**SAMPLE_CHANNEL, "thumbnails": []}
        ch = channel_to_feed(channel)
        assert _find(ch, f"{ITUNES_NS}image") is None

    def test_empty_channel_fields(self) -> None:
        """Gracefully handles a channel dict with all-empty fields."""
        channel = {
            "channel": "",
            "description": "",
            "thumbnails": [],
            "webpage_url": "",
            "epoch": 0,
            "videos": [],
        }
        ch = channel_to_feed(channel)
        assert _text(ch, "title") == ""
        assert _text(ch, "link") == ""
        assert _text(ch, "description") == ""
        assert _find(ch, "lastBuildDate") is None
        assert _find(ch, f"{ITUNES_NS}image") is None

    def test_serialisable_to_xml(self) -> None:
        """The returned Element should produce valid XML when serialised."""
        ch = channel_to_feed(SAMPLE_CHANNEL, feed_url="https://example.com/feed.xml")
        xml_bytes = tostring(ch, encoding="unicode")
        assert "<channel" in xml_bytes
        assert "</channel>" in xml_bytes
        assert "Rick Astley" in xml_bytes
        assert "https://www.youtube.com/@RickAstleyYT" in xml_bytes

    def test_videos_are_ignored(self) -> None:
        """The videos list should not appear anywhere in the feed output."""
        ch = channel_to_feed(SAMPLE_CHANNEL)
        xml_str = tostring(ch, encoding="unicode")
        for vid in SAMPLE_CHANNEL["videos"]:
            assert vid not in xml_str
