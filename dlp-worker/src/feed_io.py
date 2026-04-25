"""Read and write the per-feed XML document in R2."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from xml.etree.ElementTree import fromstring

from pyodide.ffi import JsProxy

from feed.channel import YTCAST_NS
from helpers import to_js
from ytcast_shared import feed_path


@dataclass(frozen=True)
class ExistingFeed:
    """Snapshot of the persisted feed document we care about."""

    channel_id: str | None
    last_built: datetime | None


async def read_existing_feed(env: JsProxy, feed_id: str) -> ExistingFeed | None:
    """Return the parsed channel-id / last-build from the stored feed.

    Returns ``None`` when no feed has been written yet. Always returns
    an :class:`ExistingFeed` (with ``None`` fields) when the document
    exists but lacks the relevant elements — that lets the caller
    distinguish "first run" from "feed exists but missing metadata".
    """
    obj: JsProxy = await env.STORAGE.get(feed_path(feed_id))
    if not obj:
        return None

    body = await obj.text()
    try:
        root = fromstring(str(body))
    except Exception:
        return ExistingFeed(channel_id=None, last_built=None)

    channel_el = root.find("channel")
    if channel_el is None:
        return ExistingFeed(channel_id=None, last_built=None)

    channel_id_el = channel_el.find(f"{{{YTCAST_NS}}}channelId")
    channel_id = channel_id_el.text if channel_id_el is not None else None

    last_built: datetime | None = None
    last_build_el = channel_el.find("lastBuildDate")
    if last_build_el is not None and last_build_el.text:
        try:
            last_built = parsedate_to_datetime(last_build_el.text)
        except (TypeError, ValueError):
            last_built = None

    return ExistingFeed(channel_id=channel_id, last_built=last_built)


async def write_feed(env: JsProxy, feed_id: str, body: bytes) -> None:
    """Write *body* to the feed.xml R2 key for *feed_id*."""
    await env.STORAGE.put(
        feed_path(feed_id),
        to_js(body),
        to_js(
            {"httpMetadata": to_js({"contentType": "application/rss+xml"})},
        ),
    )
