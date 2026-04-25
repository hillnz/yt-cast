"""Read and write the per-feed XML document in R2."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pyodide.ffi import JsProxy

from helpers import to_js
from ytcast_shared import feed_path


@dataclass(frozen=True)
class ExistingFeed:
    """Snapshot of the persisted feed metadata we care about."""

    channel_id: str | None
    last_built: datetime | None


def _custom_str(custom: JsProxy | None, key: str) -> str | None:
    if custom is None:
        return None
    value = getattr(custom, key, None)
    if value is None:
        return None
    text = str(value)
    return text or None


async def read_existing_feed(env: JsProxy, feed_id: str) -> ExistingFeed | None:
    """Return the metadata for the stored feed, or ``None`` if missing.

    Returns an :class:`ExistingFeed` with ``None`` fields when the feed
    exists but lacks the relevant metadata, so the caller can
    distinguish "first run" from "feed exists but missing metadata".
    """
    obj: JsProxy = await env.STORAGE.head(feed_path(feed_id))
    if not obj:
        return None

    custom = getattr(obj, "customMetadata", None)
    channel_id = _custom_str(custom, "channelId")
    last_built_raw = _custom_str(custom, "lastBuilt")

    last_built: datetime | None = None
    if last_built_raw:
        try:
            last_built = datetime.fromisoformat(last_built_raw)
        except ValueError:
            last_built = None

    return ExistingFeed(channel_id=channel_id, last_built=last_built)


async def write_feed(
    env: JsProxy,
    feed_id: str,
    body: bytes,
    *,
    channel_id: str,
    last_built: datetime,
) -> None:
    """Write *body* to the feed.xml R2 key for *feed_id*."""
    await env.STORAGE.put(
        feed_path(feed_id),
        to_js(body),
        to_js(
            {
                "httpMetadata": to_js({"contentType": "application/rss+xml"}),
                "customMetadata": to_js(
                    {
                        "channelId": channel_id,
                        "lastBuilt": last_built.isoformat(),
                    }
                ),
            },
        ),
    )
