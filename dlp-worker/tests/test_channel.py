"""Tests for the podcast feed channel module."""

from __future__ import annotations

from datetime import datetime, timezone
from xml.etree.ElementTree import Element, tostring

from feed.channel import (
    YTCAST_NS,
    _pick_best_thumbnail,
    channel_to_feed,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ITUNES_NS = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"
ATOM_NS = "{http://www.w3.org/2005/Atom}"
YTCAST = f"{{{YTCAST_NS}}}"


def _find(element: Element, tag: str) -> Element | None:
    return element.find(tag)


def _text(element: Element, tag: str) -> str | None:
    child = _find(element, tag)
    return child.text if child is not None and child.text is not None else None


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

LAST_BUILT = datetime(2024, 7, 3, 9, 46, 40, tzinfo=timezone.utc)


def _build(**overrides) -> Element:
    kwargs = {
        "channel_id": "@RickAstleyYT",
        "last_built": LAST_BUILT,
    }
    kwargs.update(overrides)
    return channel_to_feed(SAMPLE_CHANNEL, **kwargs)


# ---------------------------------------------------------------------------
# _pick_best_thumbnail
# ---------------------------------------------------------------------------


class TestPickBestThumbnail:
    def test_picks_largest_area(self) -> None:
        assert (
            _pick_best_thumbnail(SAMPLE_THUMBNAILS)
            == "https://i.ytimg.com/vi/dQ/thumb3.jpg"
        )

    def test_empty_list(self) -> None:
        assert _pick_best_thumbnail([]) is None

    def test_no_dimensions_falls_back_to_last(self) -> None:
        thumbs = [
            {"url": "https://example.com/small.jpg", "width": None, "height": None},
            {"url": "https://example.com/big.jpg", "width": None, "height": None},
        ]
        assert _pick_best_thumbnail(thumbs) == "https://example.com/big.jpg"

    def test_missing_url_returns_none(self) -> None:
        thumbs = [{"url": "", "width": 100, "height": 100}]
        assert _pick_best_thumbnail(thumbs) is None


# ---------------------------------------------------------------------------
# channel_to_feed
# ---------------------------------------------------------------------------


class TestChannelToFeed:
    def test_returns_element(self) -> None:
        ch = _build()
        assert isinstance(ch, Element)
        assert ch.tag == "channel"

    def test_title(self) -> None:
        assert _text(_build(), "title") == "Rick Astley"

    def test_link(self) -> None:
        assert _text(_build(), "link") == "https://www.youtube.com/@RickAstleyYT"

    def test_description(self) -> None:
        assert (
            _text(_build(), "description") == "Official YouTube channel of Rick Astley."
        )

    def test_last_build_date_uses_supplied_timestamp(self) -> None:
        assert _text(_build(), "lastBuildDate") == "Wed, 03 Jul 2024 09:46:40 +0000"

    def test_channel_id_round_trip(self) -> None:
        assert _text(_build(channel_id="@SomeHandle"), f"{YTCAST}channelId") == (
            "@SomeHandle"
        )

    def test_no_items(self) -> None:
        assert _build().find("item") is None

    def test_itunes_author(self) -> None:
        assert _text(_build(), f"{ITUNES_NS}author") == "Rick Astley"

    def test_itunes_explicit(self) -> None:
        assert _text(_build(), f"{ITUNES_NS}explicit") == "false"

    def test_itunes_image(self) -> None:
        img = _find(_build(), f"{ITUNES_NS}image")
        assert img is not None
        assert img.get("href") == "https://i.ytimg.com/vi/dQ/thumb3.jpg"

    def test_itunes_category(self) -> None:
        cat = _find(_build(), f"{ITUNES_NS}category")
        assert cat is not None
        assert cat.get("text") == "Arts"

    def test_atom_self_link(self) -> None:
        ch = _build(feed_url="https://example.com/feed.xml")
        atom_link = _find(ch, f"{ATOM_NS}link")
        assert atom_link is not None
        assert atom_link.get("href") == "https://example.com/feed.xml"
        assert atom_link.get("rel") == "self"
        assert atom_link.get("type") == "application/rss+xml"

    def test_no_atom_link_when_feed_url_empty(self) -> None:
        assert _find(_build(), f"{ATOM_NS}link") is None

    def test_no_thumbnails_omits_itunes_image(self) -> None:
        channel = {**SAMPLE_CHANNEL, "thumbnails": []}
        ch = channel_to_feed(channel, channel_id="@x", last_built=LAST_BUILT)
        assert _find(ch, f"{ITUNES_NS}image") is None

    def test_serialisable_to_xml(self) -> None:
        ch = _build(feed_url="https://example.com/feed.xml")
        xml_str = tostring(ch, encoding="unicode")
        assert "<channel" in xml_str
        assert "</channel>" in xml_str
        assert "Rick Astley" in xml_str

    def test_videos_are_ignored(self) -> None:
        xml_str = tostring(_build(), encoding="unicode")
        for vid in SAMPLE_CHANNEL["videos"]:
            assert vid not in xml_str
