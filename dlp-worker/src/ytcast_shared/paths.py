"""R2 storage key conventions shared across workers."""

from __future__ import annotations


def feed_path(feed_id: str) -> str:
    """R2 key for a feed's XML document."""
    return f"{feed_id}/feed.xml"


def video_path(feed_id: str, video_id: str) -> str:
    """R2 key for a downloaded video's audio under *feed_id*."""
    return f"{feed_id}/{video_id}"
