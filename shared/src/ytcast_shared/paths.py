"""R2 storage key conventions shared across workers."""

from __future__ import annotations


def feed_path(feed_id: str) -> str:
    """R2 key for a feed's XML document."""
    return f"{feed_id}/feed.xml"


def video_path(feed_id: str, video_id: str, bucket: str) -> str:
    """R2 key for a downloaded video's audio.

    *bucket* is the lifecycle prefix (see ``expiry.expiry_bucket``)
    that controls how long R2 retains the object.
    """
    return f"{bucket}/{feed_id}/{video_id}"
