"""YouTube download functionality using yt-dlp as a Python library."""

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from urllib.parse import quote

import yt_dlp
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class YtDlError(Exception):
    """Base error for yt-dlp operations."""


class ItemNotFoundError(YtDlError):
    """Raised when a YouTube item (channel, video, etc.) is not found."""


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Thumbnail(BaseModel):
    """A YouTube thumbnail."""

    url: str
    width: int | None = None
    height: int | None = None


class Channel(BaseModel):
    """YouTube channel metadata."""

    channel: str
    description: str
    thumbnails: list[Thumbnail]
    webpage_url: str
    videos_url: str = ""
    epoch: int


class Video(BaseModel):
    """YouTube video metadata."""

    id: str
    title: str
    description: str
    upload_date: str
    duration: str


# ---------------------------------------------------------------------------
# YtDl service
# ---------------------------------------------------------------------------


class YtDl:
    """Interface to yt-dlp functionality using the Python library directly."""

    # -- URL helpers --------------------------------------------------------

    @staticmethod
    def _get_channel_url(channel_name: str, page: str) -> str:
        return f"https://www.youtube.com/c/{quote(channel_name)}/{quote(page)}"

    @staticmethod
    def _get_channel_id_url(channel_id: str, page: str) -> str:
        return f"https://www.youtube.com/channel/{quote(channel_id)}/{quote(page)}"

    @staticmethod
    def _get_user_url(channel_name: str, page: str) -> str:
        return f"https://www.youtube.com/user/{quote(channel_name)}/{quote(page)}"

    @staticmethod
    def _get_handle_url(channel_name: str, page: str) -> str:
        return f"https://www.youtube.com/@{quote(channel_name)}/{quote(page)}"

    # -- Internal helpers ---------------------------------------------------

    @staticmethod
    def _extract_info(url: str, ydl_opts: dict | None = None) -> dict:
        """Extract info synchronously using yt-dlp (blocking)."""
        opts: dict = {
            "quiet": True,
            "no_warnings": True,
            **(ydl_opts or {}),
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if info is None:
            raise ItemNotFoundError(f"No info returned for URL: {url}")
        return info

    @staticmethod
    def _is_not_found(exc: yt_dlp.utils.DownloadError) -> bool:
        """Return *True* if the download error indicates a 404 / not-found."""
        msg = str(exc).lower()
        return (
            "404" in msg
            or "not found" in msg
            or "does not exist" in msg
            or "video unavailable" in msg
        )

    # -- Public API ---------------------------------------------------------

    async def get_channel_info(self, channel_name: str) -> Channel:
        """Fetch channel metadata, trying multiple URL patterns.

        Raises :class:`ItemNotFoundError` if none of the URLs resolve.
        """
        logger.debug("get_channel_info(%s)", channel_name)

        candidate_urls = [
            (
                self._get_handle_url(channel_name, "about"),
                self._get_handle_url(channel_name, "videos"),
            ),
            (
                self._get_channel_url(channel_name, "about"),
                self._get_channel_url(channel_name, "videos"),
            ),
            (
                self._get_user_url(channel_name, "about"),
                self._get_user_url(channel_name, "videos"),
            ),
            (
                self._get_channel_id_url(channel_name, "about"),
                self._get_channel_id_url(channel_name, "videos"),
            ),
        ]

        for about_url, videos_url in candidate_urls:
            try:
                info = await asyncio.to_thread(
                    self._extract_info,
                    about_url,
                    {"extract_flat": True},
                )
            except yt_dlp.utils.DownloadError as exc:
                if self._is_not_found(exc):
                    continue
                raise YtDlError(str(exc)) from exc
            except ItemNotFoundError:
                continue

            thumbnails = [
                Thumbnail(
                    url=t["url"],
                    width=t.get("width"),
                    height=t.get("height"),
                )
                for t in info.get("thumbnails", [])
            ]

            return Channel(
                channel=info.get("channel", info.get("uploader", "")),
                description=info.get("description", ""),
                thumbnails=thumbnails,
                webpage_url=info.get("webpage_url", about_url),
                videos_url=videos_url,
                epoch=info.get("epoch", 0),
            )

        raise ItemNotFoundError(f"Channel not found: {channel_name}")

    async def get_channel_videos(
        self,
        channel_info: Channel,
        limit: int = 5,
    ) -> list[str]:
        """Fetch recent video IDs from a channel.

        Returns up to *limit* video IDs from the channel's videos page.
        Uses flat extraction (``extract_flat=True``) for speed; use
        :meth:`get_video_info` to retrieve full metadata for each ID.
        """
        logger.debug("get_channel_videos(%s, limit=%d)", channel_info.channel, limit)

        opts: dict = {
            "extract_flat": True,
            "playlistend": limit,
            "dateafter": "now-1week",
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "process": False,
        }

        info = await asyncio.to_thread(
            self._extract_info,
            channel_info.videos_url,
            opts,
        )

        video_ids: list[str] = []
        for entry in info.get("entries", []):
            if entry is None:
                continue
            video_id = entry.get("id", "")
            if video_id:
                video_ids.append(video_id)

        return video_ids

    async def get_video_info(self, video_id: str) -> Video:
        """Fetch metadata for a single YouTube video by its ID.

        Returns a :class:`Video` object with the same fields that
        :meth:`get_channel_videos` produces for each entry.
        """
        logger.debug("get_video_info(%s)", video_id)

        url = f"https://www.youtube.com/watch?v={quote(video_id)}"

        try:
            info = await asyncio.to_thread(self._extract_info, url)
        except yt_dlp.utils.DownloadError as exc:
            if self._is_not_found(exc):
                raise ItemNotFoundError(f"Video not found: {video_id}") from exc
            raise YtDlError(str(exc)) from exc

        return Video(
            id=info.get("id", video_id),
            title=info.get("title", ""),
            description=info.get("description", ""),
            upload_date=info.get("upload_date", ""),
            duration=info.get("duration_string", ""),
        )

    async def download_audio(
        self,
        video_id: str,
        output: Path,
        *,
        sponsorblock_categories: list[str] | None = None,
    ) -> None:
        """Download and extract audio for a YouTube video.

        Uses SponsorBlock to strip *sponsorblock_categories* (defaults to
        ``["sponsor", "selfpromo"]`` to match the original Rust behaviour).
        """
        logger.debug("download_audio(%s, %s)", video_id, output)

        url = f"https://www.youtube.com/watch?v={quote(video_id)}"
        categories = sponsorblock_categories or ["sponsor", "selfpromo"]

        opts: dict = {
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "m4a",
                },
                {
                    "key": "SponsorBlock",
                    "categories": categories,
                },
                {
                    "key": "ModifyChapters",
                    "remove_sponsor_segments": categories,
                },
            ],
            "outtmpl": str(output),
            "quiet": True,
            "no_warnings": True,
        }

        def _download() -> None:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])

        try:
            await asyncio.to_thread(_download)
        except yt_dlp.utils.DownloadError as exc:
            if self._is_not_found(exc):
                raise ItemNotFoundError(f"Video not found: {video_id}") from exc
            raise YtDlError(str(exc)) from exc


# ---------------------------------------------------------------------------
# Adhoc CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG, format="%(name)s %(levelname)s %(message)s"
    )

    parser = argparse.ArgumentParser(description="Adhoc testing for ytdl.py")
    sub = parser.add_subparsers(dest="command", required=True)

    # -- channel-info -------------------------------------------------------
    ch = sub.add_parser("channel", help="Fetch channel info")
    ch.add_argument("name", help="Channel name, handle, or ID")

    # -- channel-videos -----------------------------------------------------
    cv = sub.add_parser("videos", help="Fetch recent videos for a channel")
    cv.add_argument("name", help="Channel name, handle, or ID")
    cv.add_argument("--limit", type=int, default=5, help="Max videos to fetch")

    # -- download-audio -----------------------------------------------------
    vi = sub.add_parser("video", help="Fetch info for a single video")
    vi.add_argument("video_id", help="YouTube video ID")

    # -- download-audio -----------------------------------------------------
    dl = sub.add_parser("download", help="Download audio for a video")
    dl.add_argument("video_id", help="YouTube video ID")
    dl.add_argument(
        "-o",
        "--output",
        default="%(title)s.%(ext)s",
        help="Output template (yt-dlp style)",
    )

    args = parser.parse_args()
    svc = YtDl()

    async def _main() -> None:
        if args.command == "channel":
            info = await svc.get_channel_info(args.name)
            print(info.model_dump_json(indent=2))

        elif args.command == "videos":
            info = await svc.get_channel_info(args.name)
            video_ids = await svc.get_channel_videos(info, limit=args.limit)
            for vid in video_ids:
                print(vid)

        elif args.command == "video":
            video = await svc.get_video_info(args.video_id)
            print(video.model_dump_json(indent=2))

        elif args.command == "download":
            await svc.download_audio(args.video_id, Path(args.output))
            print(f"Downloaded {args.video_id} -> {args.output}")

    sys.exit(asyncio.run(_main()))
