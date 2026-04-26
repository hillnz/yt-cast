"""Top-level orchestration for queue messages.

A message carries either ``channel`` (the YouTube channel handle/ID
the user requested) or ``feed_id`` (an existing feed reference). We
resolve one to the other via the stored feed.xml when needed, throttle
rebuilds to once per hour, then refresh the audio cache and republish
the feed.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
from js import console
from pyodide.ffi import JsProxy

from dlp import DlpClient, DlpConfig, DlpError, DlpNotFoundError
from download import (
    VideoDownloadError,
    download_video,
    existing_segment_hash,
    head_video,
)
from feed.channel import ChannelData
from feed.item import VideoData
from feed_builder import build_feed
from feed_io import read_existing_feed, write_feed
from sponsorblock import (
    SponsorBlockError,
    fetch_segment_timestamps,
    hash_segment_timestamps,
)
from ytcast_shared import get_feed_id, video_path

# Hard cap on how many recent videos we surface per feed. Bounds Drive +
# DLP work per build; podcast clients typically only show a window.
MAX_VIDEOS_PER_CHANNEL = 10

# Don't rebuild a feed more than once per this interval. Manually-triggered
# refreshes still bypass this if the stored feed has no last-build date.
MIN_REBUILD_INTERVAL = timedelta(hours=1)

# Concurrency for parallel /video/{id} metadata fetches.
_DEFAULT_VIDEO_FETCH_CONCURRENCY = 4

# Env vars that must be set for any message to be processable. If any is
# missing the deploy is broken — retrying won't help, so we drop the
# message rather than spin on it until the queue retry budget is exhausted.
_REQUIRED_ENV_VARS: tuple[str, ...] = (
    "DLP_URL",
    "R2_PUBLIC_URL",
    "DRIVE_ROOT_ID",
    "FEED_ID_SECRET",
    "GOOGLE_SERVICE_ACCOUNT",
)


class PermanentMessageError(Exception):
    """Raised when a queue message cannot be processed and retrying won't
    help (e.g. misconfiguration, malformed input). The entrypoint acks
    these messages so they are dropped from the queue."""


def _validate_env(env: JsProxy) -> None:
    missing = [
        name
        for name in _REQUIRED_ENV_VARS
        if not str(getattr(env, name, "") or "")
    ]
    if missing:
        raise PermanentMessageError(
            "Required env vars not configured: " + ", ".join(missing)
        )


@dataclass(frozen=True)
class QueueInput:
    channel: str | None
    feed_id: str | None


def _parse_message(body: object) -> QueueInput:
    """Read ``channel`` / ``feed_id`` off a JS message body."""
    channel = getattr(body, "channel", None)
    feed_id = getattr(body, "feed_id", None)
    return QueueInput(
        channel=str(channel) if channel else None,
        feed_id=str(feed_id) if feed_id else None,
    )


async def _fetch_video_bounded(
    client: DlpClient,
    video_id: str,
    sem: asyncio.Semaphore,
) -> VideoData | None:
    async with sem:
        try:
            return await client.get_video(video_id)
        except DlpNotFoundError:
            console.warn(f"DLP video metadata missing, skipping: {video_id}")
            return None
        except DlpError as exc:
            console.error(f"DLP video metadata fetch failed for {video_id}: {exc}")
            return None


async def _fetch_video_metadata(
    client: DlpClient, video_ids: list[str], concurrency: int
) -> list[VideoData]:
    if not video_ids:
        return []
    sem = asyncio.Semaphore(concurrency)
    results = await asyncio.gather(
        *(_fetch_video_bounded(client, vid, sem) for vid in video_ids),
    )
    return [v for v in results if v is not None]


def _public_audio_url(env: JsProxy, feed_id: str, video_id: str) -> str:
    """Build the public R2 URL for a downloaded video."""
    base = str(getattr(env, "R2_PUBLIC_URL", "") or "").rstrip("/")
    if not base:
        raise RuntimeError("R2_PUBLIC_URL env var is not configured")
    return f"{base}/{video_path(feed_id, video_id)}"


async def _ensure_videos_cached(
    env: JsProxy,
    *,
    dlp: DlpClient,
    feed_id: str,
    videos: list[VideoData],
) -> None:
    """Download videos missing from R2 or whose SponsorBlock segments have
    changed. Failures are logged, not raised."""
    async with httpx.AsyncClient(timeout=30.0) as sb_client:
        for video in videos:
            video_id = video["id"]
            head = await head_video(env, feed_id, video_id)

            try:
                segments = await fetch_segment_timestamps(sb_client, video_id)
                new_hash = hash_segment_timestamps(segments)
            except SponsorBlockError as exc:
                if head is not None:
                    console.warn(
                        f"SponsorBlock unavailable for {video_id}, "
                        + f"keeping cached file: {exc}"
                    )
                    continue
                console.warn(
                    f"SponsorBlock unavailable for {video_id}, "
                    + f"downloading without hash: {exc}"
                )
                # Empty hash → next run with a working SB sees no stored hash
                # and will refresh the file.
                new_hash = ""

            old_hash = existing_segment_hash(head)
            if head is not None and old_hash == new_hash:
                continue

            try:
                await download_video(
                    env,
                    dlp=dlp,
                    feed_id=feed_id,
                    video_id=video_id,
                    segment_hash=new_hash,
                )
            except (DlpError, VideoDownloadError) as exc:
                console.error(f"Skipping {video_id}: {exc}")


async def _rebuild_feed(
    env: JsProxy,
    *,
    feed_id: str,
    channel_id: str,
) -> None:
    """Fetch channel + videos, refresh audio cache, write feed.xml."""
    config = DlpConfig.from_env(env)
    now = datetime.now(timezone.utc)

    async with DlpClient(config) as dlp:
        try:
            channel: ChannelData = await dlp.get_channel(channel_id)
        except DlpNotFoundError:
            console.warn(f"Channel not found in DLP: {channel_id}")
            return

        video_ids = list(channel.get("videos") or [])[:MAX_VIDEOS_PER_CHANNEL]
        console.log(
            f"Building feed_id={feed_id} channel={channel_id}: "
            + f"{len(video_ids)} videos"
        )

        videos = await _fetch_video_metadata(
            dlp, video_ids, _DEFAULT_VIDEO_FETCH_CONCURRENCY
        )

        await _ensure_videos_cached(env, dlp=dlp, feed_id=feed_id, videos=videos)

    def audio_url_for(video: VideoData) -> str:
        return _public_audio_url(env, feed_id, video["id"])

    body = build_feed(
        channel=channel,
        videos=videos,
        audio_url_for=audio_url_for,
        last_built=now,
    )
    await write_feed(env, feed_id, body, channel_id=channel_id, last_built=now)
    console.log(f"Feed published: feed_id={feed_id}")


async def process_message(env: JsProxy, body: object) -> None:
    """Handle a single queue message end-to-end."""
    _validate_env(env)
    msg = _parse_message(body)

    if msg.channel:
        feed_id = get_feed_id(msg.channel, str(env.FEED_ID_SECRET))
        channel_id: str | None = msg.channel
    elif msg.feed_id:
        feed_id = msg.feed_id
        channel_id = None
    else:
        console.warn("Queue message missing both channel and feed_id, skipping")
        return

    existing = await read_existing_feed(env, feed_id)

    if existing is not None:
        if existing.last_built is not None:
            age = datetime.now(timezone.utc) - existing.last_built
            if age < MIN_REBUILD_INTERVAL:
                console.log(
                    f"Feed {feed_id} rebuilt {age} ago (< {MIN_REBUILD_INTERVAL}); "
                    + "skipping"
                )
                return
        if channel_id is None:
            channel_id = existing.channel_id

    if channel_id is None:
        console.log(
            f"Feed {feed_id} has no stored channel and message lacks one; nothing to do"
        )
        return

    await _rebuild_feed(env, feed_id=feed_id, channel_id=channel_id)
