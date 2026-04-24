"""Build a podcast RSS feed from the DLP archive service.

Glues together the :mod:`dlp` HTTP client and the converters in the
:mod:`feed` package: fetches a channel, fans out to ``/video/{id}``
calls in parallel (with a configurable concurrency cap), and emits a
serialised RSS document with one ``<item>`` per video.

HTTP concerns (request parsing, status codes, response shaping) live in
``handler.py`` — this module raises typed errors and returns ``bytes``.
"""

from __future__ import annotations

import asyncio
from xml.etree.ElementTree import Element, tostring

from js import console

from dlp import DlpClient, DlpConfig, DlpError, DlpNotFoundError
from feed import channel_to_feed, video_to_item
from feed.item import VideoData

# Default concurrency for parallel /video/{id} fetches when
# ``DLP_CONCURRENCY`` is unset or invalid.
_DEFAULT_CONCURRENCY = 8

# iTunes podcast namespace, mirrored from feed.channel/feed.item so we
# can register it on the root <rss> element for clean serialisation.
_ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
_ATOM_NS = "http://www.w3.org/2005/Atom"


class FeedBuildError(Exception):
    """Base class for errors raised while building a podcast feed."""


class FeedNotFoundError(FeedBuildError):
    """Raised when the requested channel does not exist in DLP."""


def _resolve_concurrency(env: object) -> int:
    """Read ``DLP_CONCURRENCY`` from *env*, falling back to the default."""
    raw = getattr(env, "DLP_CONCURRENCY", None)
    if not raw:
        return _DEFAULT_CONCURRENCY

    try:
        value = int(str(raw))
    except ValueError:
        return _DEFAULT_CONCURRENCY

    return value if value > 0 else _DEFAULT_CONCURRENCY


async def _fetch_video_bounded(
    client: DlpClient,
    video_id: str,
    sem: asyncio.Semaphore,
) -> VideoData | None:
    """Fetch a single video, returning ``None`` on per-video failure.

    A failure for one video should not poison the whole feed, so
    individual errors are logged and the video is skipped.
    """
    async with sem:
        try:
            return await client.get_video(video_id)
        except DlpNotFoundError:
            console.warn(f"DLP video not found, skipping: {video_id}")
            return None
        except DlpError as exc:
            console.error(f"DLP video fetch failed for {video_id}: {exc}")
            return None


async def _fetch_videos(
    client: DlpClient,
    video_ids: list[str],
    concurrency: int,
) -> list[VideoData]:
    """Fetch all *video_ids* in parallel, capped at *concurrency* in flight.

    Preserves input order in the returned list and drops any videos
    whose fetch failed.
    """
    if not video_ids:
        return []

    sem = asyncio.Semaphore(concurrency)
    results = await asyncio.gather(
        *(_fetch_video_bounded(client, vid, sem) for vid in video_ids),
    )
    return [v for v in results if v is not None]


def _audio_url_for(worker_base_url: str, video_id: str) -> str:
    """Build the worker-hosted audio enclosure URL for *video_id*."""
    return f"{worker_base_url.rstrip('/')}/download/{video_id}"


def _build_rss_document(
    channel_element: Element,
    item_elements: list[Element],
) -> bytes:
    """Wrap *channel_element* + *item_elements* in an ``<rss>`` root.

    Returns the serialised XML as ``bytes`` (UTF-8, with XML
    declaration) ready to hand to a :class:`Response`.
    """
    rss = Element(
        "rss",
        attrib={
            "version": "2.0",
            "xmlns:itunes": _ITUNES_NS,
            "xmlns:atom": _ATOM_NS,
        },
    )

    # Append items to the channel before nesting it under <rss>.
    for item in item_elements:
        channel_element.append(item)

    rss.append(channel_element)

    return tostring(
        rss,
        encoding="utf-8",
        xml_declaration=True,
        short_empty_elements=True,
    )


async def build_channel_feed(
    env: object,
    channel_id: str,
    *,
    worker_base_url: str,
    feed_url: str = "",
) -> bytes:
    """Build a podcast RSS feed for *channel_id*.

    Parameters
    ----------
    env:
        The Workers ``env`` JsProxy. Used to read DLP configuration.
    channel_id:
        The YouTube channel ID / handle / name to look up via DLP.
    worker_base_url:
        Base URL of *this* worker (e.g. ``"https://worker.example.com"``).
        Used to construct ``/download/{video_id}`` enclosure URLs.
    feed_url:
        Canonical URL of this feed. Populates the Atom self-link in the
        generated channel.

    Returns
    -------
    bytes
        Serialised RSS 2.0 XML document (UTF-8) ready to send.

    Raises
    ------
    FeedNotFoundError
        If the channel does not exist in DLP.
    FeedBuildError
        For other DLP / build failures.
    """
    config = DlpConfig.from_env(env)
    concurrency = _resolve_concurrency(env)

    async with DlpClient(config) as client:
        try:
            channel_data = await client.get_channel(channel_id)
        except DlpNotFoundError as exc:
            raise FeedNotFoundError(str(exc)) from exc
        except DlpError as exc:
            raise FeedBuildError(str(exc)) from exc

        video_ids = list(channel_data.get("videos") or [])
        console.log(
            f"Building feed for channel {channel_id}: "
            + f"{len(video_ids)} videos, concurrency={concurrency}"
        )

        videos = await _fetch_videos(client, video_ids, concurrency)

    channel_element = channel_to_feed(channel_data, feed_url=feed_url)
    item_elements = [
        video_to_item(video, _audio_url_for(worker_base_url, video["id"]))
        for video in videos
    ]

    return _build_rss_document(channel_element, item_elements)
