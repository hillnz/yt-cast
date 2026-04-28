"""Tests for the ytdl module."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yt_dlp

from app.ytdl import (
    Channel,
    Format,
    ItemNotFoundError,
    Thumbnail,
    Video,
    YtDl,
    YtDlAuthError,
    YtDlError,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ytdl() -> YtDl:
    """Return a fresh YtDl instance."""
    return YtDl()


@pytest.fixture
def sample_channel_info() -> dict:
    """Return a dict resembling yt-dlp channel extract_info output."""
    return {
        "channel": "Techmoan",
        "description": "A channel about tech reviews.",
        "thumbnails": [
            {"url": "https://example.com/thumb.jpg", "width": 100, "height": 100},
            {"url": "https://example.com/thumb_big.jpg", "width": 800, "height": 800},
        ],
        "webpage_url": "https://www.youtube.com/c/Techmoan/about",
        "epoch": 1700000000,
    }


@pytest.fixture
def sample_channel() -> Channel:
    """Return a Channel model for use in get_channel_videos tests."""
    return Channel(
        channel="Techmoan",
        description="A channel about tech reviews.",
        thumbnails=[
            Thumbnail(url="https://example.com/thumb.jpg", width=100, height=100),
        ],
        webpage_url="https://www.youtube.com/c/Techmoan/about",
        videos_url="https://www.youtube.com/c/Techmoan/videos",
        epoch=1700000000,
    )


@pytest.fixture
def sample_video_entries() -> list[dict]:
    """Return a list of dicts resembling yt-dlp video entries."""
    return [
        {
            "id": "abc123",
            "title": "First Video",
            "description": "Description of the first video.",
            "upload_date": "20240101",
            "uploader": "Techmoan",
            "duration_string": "12:34",
        },
        {
            "id": "def456",
            "title": "Second Video",
            "description": "Description of the second video.",
            "upload_date": "20240102",
            "uploader": "Techmoan",
            "duration_string": "5:00",
        },
    ]


# ---------------------------------------------------------------------------
# URL helper tests
# ---------------------------------------------------------------------------


class TestUrlHelpers:
    """Tests for the static URL builder methods."""

    def test_get_channel_url(self) -> None:
        url = YtDl._get_channel_url("Techmoan", "about")
        assert url == "https://www.youtube.com/c/Techmoan/about"

    def test_get_channel_url_encodes_special_chars(self) -> None:
        url = YtDl._get_channel_url("name with spaces", "videos")
        assert "name%20with%20spaces" in url

    def test_get_channel_id_url(self) -> None:
        url = YtDl._get_channel_id_url("UC12345", "about")
        assert url == "https://www.youtube.com/channel/UC12345/about"

    def test_get_user_url(self) -> None:
        url = YtDl._get_user_url("someuser", "videos")
        assert url == "https://www.youtube.com/user/someuser/videos"


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestModels:
    """Tests for the Pydantic data models."""

    def test_thumbnail_optional_dimensions(self) -> None:
        t = Thumbnail(url="https://example.com/img.jpg")
        assert t.width is None
        assert t.height is None

    def test_thumbnail_with_dimensions(self) -> None:
        t = Thumbnail(url="https://example.com/img.jpg", width=120, height=90)
        assert t.width == 120
        assert t.height == 90

    def test_channel_defaults(self) -> None:
        c = Channel(
            channel="Test",
            description="Desc",
            thumbnails=[],
            webpage_url="https://example.com",
            epoch=0,
        )
        assert c.videos_url == ""

    def test_video_fields(self) -> None:
        v = Video(
            id="abc",
            title="Title",
            description="Desc",
            upload_date="20240101",
            uploader="Uploader",
            duration="1:23",
        )
        assert v.id == "abc"
        assert v.duration == "1:23"


# ---------------------------------------------------------------------------
# get_channel_info tests
# ---------------------------------------------------------------------------


class TestGetChannelInfo:
    """Tests for YtDl.get_channel_info."""

    @pytest.mark.asyncio
    async def test_returns_channel_on_first_url_match(
        self, ytdl: YtDl, sample_channel_info: dict
    ) -> None:
        with patch.object(YtDl, "_extract_info", return_value=sample_channel_info):
            channel = await ytdl.get_channel_info("Techmoan")

        assert channel.channel == "Techmoan"
        assert channel.description == "A channel about tech reviews."
        assert len(channel.thumbnails) == 2
        assert channel.thumbnails[0].width == 100
        assert channel.epoch == 1700000000
        assert channel.videos_url == "https://www.youtube.com/@Techmoan/videos"

    @pytest.mark.asyncio
    async def test_falls_through_to_c_url_on_404(
        self, ytdl: YtDl, sample_channel_info: dict
    ) -> None:
        """If the @handle URL 404s, the /c/ URL should be tried."""
        call_count = 0

        def fake_extract(url: str, opts: dict | None = None) -> dict:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise yt_dlp.utils.DownloadError("HTTP Error 404: Not Found")
            return sample_channel_info

        with patch.object(YtDl, "_extract_info", side_effect=fake_extract):
            channel = await ytdl.get_channel_info("Techmoan")

        assert call_count == 2
        assert channel.channel == "Techmoan"
        # videos_url should correspond to the /c/ pattern (second candidate)
        assert "/c/" in channel.videos_url

    @pytest.mark.asyncio
    async def test_falls_through_to_user_url_on_404(
        self, ytdl: YtDl, sample_channel_info: dict
    ) -> None:
        """If both @handle and /c/ fail, /user/ should be tried."""
        call_count = 0

        def fake_extract(url: str, opts: dict | None = None) -> dict:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise yt_dlp.utils.DownloadError("HTTP Error 404: Not Found")
            return sample_channel_info

        with patch.object(YtDl, "_extract_info", side_effect=fake_extract):
            channel = await ytdl.get_channel_info("UC12345")

        assert call_count == 3
        assert "/user/" in channel.videos_url

    @pytest.mark.asyncio
    async def test_falls_through_to_channel_id_url(
        self, ytdl: YtDl, sample_channel_info: dict
    ) -> None:
        """If @handle, /c/, and /user/ all 404, /channel/ should be tried."""
        call_count = 0

        def fake_extract(url: str, opts: dict | None = None) -> dict:
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                raise yt_dlp.utils.DownloadError("HTTP Error 404: Not Found")
            return sample_channel_info

        with patch.object(YtDl, "_extract_info", side_effect=fake_extract):
            channel = await ytdl.get_channel_info("UC12345")

        assert call_count == 4
        assert "/channel/" in channel.videos_url

    @pytest.mark.asyncio
    async def test_raises_item_not_found_when_all_urls_fail(self, ytdl: YtDl) -> None:
        with patch.object(
            YtDl,
            "_extract_info",
            side_effect=yt_dlp.utils.DownloadError("HTTP Error 404: Not Found"),
        ):
            with pytest.raises(ItemNotFoundError, match="Channel not found"):
                await ytdl.get_channel_info("thischannelhopefullydoesnotexist")

    @pytest.mark.asyncio
    async def test_raises_ytdl_error_on_non_404_failure(self, ytdl: YtDl) -> None:
        with patch.object(
            YtDl,
            "_extract_info",
            side_effect=yt_dlp.utils.DownloadError("HTTP Error 500: Server Error"),
        ):
            with pytest.raises(YtDlError):
                await ytdl.get_channel_info("somechannel")

    @pytest.mark.asyncio
    async def test_missing_thumbnails_yields_empty_list(self, ytdl: YtDl) -> None:
        info = {
            "channel": "Bare",
            "description": "",
            "webpage_url": "https://example.com",
            "epoch": 0,
        }
        with patch.object(YtDl, "_extract_info", return_value=info):
            channel = await ytdl.get_channel_info("Bare")

        assert channel.thumbnails == []

    @pytest.mark.asyncio
    async def test_uses_uploader_when_channel_field_missing(self, ytdl: YtDl) -> None:
        info = {
            "uploader": "FallbackName",
            "description": "",
            "thumbnails": [],
            "webpage_url": "https://example.com",
            "epoch": 0,
        }
        with patch.object(YtDl, "_extract_info", return_value=info):
            channel = await ytdl.get_channel_info("test")

        assert channel.channel == "FallbackName"


# ---------------------------------------------------------------------------
# get_channel_videos tests
# ---------------------------------------------------------------------------


class TestGetChannelVideos:
    """Tests for YtDl.get_channel_videos."""

    @pytest.mark.asyncio
    async def test_returns_video_ids(
        self,
        ytdl: YtDl,
        sample_channel: Channel,
        sample_video_entries: list[dict],
    ) -> None:
        info = {"entries": sample_video_entries}
        with patch.object(YtDl, "_extract_info", return_value=info):
            video_ids = await ytdl.get_channel_videos(sample_channel)

        assert video_ids == ["abc123", "def456"]

    @pytest.mark.asyncio
    async def test_respects_limit(
        self,
        ytdl: YtDl,
        sample_channel: Channel,
        sample_video_entries: list[dict],
    ) -> None:
        """Verify the limit is forwarded to yt-dlp opts."""
        captured_opts: dict = {}

        def capture_extract(url: str, opts: dict | None = None) -> dict:
            captured_opts.update(opts or {})
            return {"entries": sample_video_entries[:1]}

        with patch.object(YtDl, "_extract_info", side_effect=capture_extract):
            video_ids = await ytdl.get_channel_videos(sample_channel, limit=1)

        assert captured_opts.get("playlistend") == 1
        assert len(video_ids) == 1

    @pytest.mark.asyncio
    async def test_defaults_to_limit_five(
        self,
        ytdl: YtDl,
        sample_channel: Channel,
    ) -> None:
        captured_opts: dict = {}

        def capture_extract(url: str, opts: dict | None = None) -> dict:
            captured_opts.update(opts or {})
            return {"entries": []}

        with patch.object(YtDl, "_extract_info", side_effect=capture_extract):
            await ytdl.get_channel_videos(sample_channel)

        assert captured_opts.get("playlistend") == 5
        assert captured_opts.get("extract_flat") is True
        assert captured_opts.get("process") is False

    @pytest.mark.asyncio
    async def test_skips_none_entries(
        self,
        ytdl: YtDl,
        sample_channel: Channel,
        sample_video_entries: list[dict],
    ) -> None:
        info = {"entries": [sample_video_entries[0], None, sample_video_entries[1]]}
        with patch.object(YtDl, "_extract_info", return_value=info):
            video_ids = await ytdl.get_channel_videos(sample_channel)

        assert len(video_ids) == 2

    @pytest.mark.asyncio
    async def test_empty_entries(
        self,
        ytdl: YtDl,
        sample_channel: Channel,
    ) -> None:
        with patch.object(YtDl, "_extract_info", return_value={"entries": []}):
            video_ids = await ytdl.get_channel_videos(sample_channel)

        assert video_ids == []

    @pytest.mark.asyncio
    async def test_entry_without_id_is_skipped(
        self,
        ytdl: YtDl,
        sample_channel: Channel,
    ) -> None:
        """An entry with no id should be skipped."""
        info = {"entries": [{"id": "valid"}, {"title": "no id"}]}
        with patch.object(YtDl, "_extract_info", return_value=info):
            video_ids = await ytdl.get_channel_videos(sample_channel)

        assert video_ids == ["valid"]


# ---------------------------------------------------------------------------
# get_video_info tests
# ---------------------------------------------------------------------------


class TestGetVideoInfo:
    """Tests for YtDl.get_video_info."""

    @pytest.mark.asyncio
    async def test_returns_video(self, ytdl: YtDl) -> None:
        info = {
            "id": "abc123",
            "title": "A Video",
            "description": "Description of the video.",
            "upload_date": "20240101",
            "duration_string": "12:34",
        }
        with patch.object(YtDl, "_extract_info", return_value=info):
            video = await ytdl.get_video_info("abc123")

        assert video.id == "abc123"
        assert video.title == "A Video"
        assert video.description == "Description of the video."
        assert video.upload_date == "20240101"
        assert video.duration == "12:34"

    @pytest.mark.asyncio
    async def test_url_contains_encoded_video_id(self, ytdl: YtDl) -> None:
        captured_url: str = ""

        def capture_extract(url: str, opts: dict | None = None) -> dict:
            nonlocal captured_url
            captured_url = url
            return {"id": "abc123"}

        with patch.object(YtDl, "_extract_info", side_effect=capture_extract):
            await ytdl.get_video_info("abc123")

        assert "abc123" in captured_url
        assert captured_url.startswith("https://www.youtube.com/watch?v=")

    @pytest.mark.asyncio
    async def test_falls_back_to_video_id_when_id_missing(self, ytdl: YtDl) -> None:
        info = {"title": "A Video"}
        with patch.object(YtDl, "_extract_info", return_value=info):
            video = await ytdl.get_video_info("abc123")

        assert video.id == "abc123"

    @pytest.mark.asyncio
    async def test_missing_fields_default_to_empty(self, ytdl: YtDl) -> None:
        info = {"id": "abc123"}
        with patch.object(YtDl, "_extract_info", return_value=info):
            video = await ytdl.get_video_info("abc123")

        assert video.title == ""
        assert video.description == ""
        assert video.upload_date == ""
        assert video.duration == ""

    @pytest.mark.asyncio
    async def test_raises_item_not_found_on_404(self, ytdl: YtDl) -> None:
        with patch.object(
            YtDl,
            "_extract_info",
            side_effect=yt_dlp.utils.DownloadError("Video unavailable"),
        ):
            with pytest.raises(ItemNotFoundError):
                await ytdl.get_video_info("abc123")

    @pytest.mark.asyncio
    async def test_raises_item_not_found_on_not_found(self, ytdl: YtDl) -> None:
        with patch.object(
            YtDl,
            "_extract_info",
            side_effect=yt_dlp.utils.DownloadError("404: not found"),
        ):
            with pytest.raises(ItemNotFoundError):
                await ytdl.get_video_info("abc123")

    @pytest.mark.asyncio
    async def test_raises_ytdl_error_on_other_download_error(self, ytdl: YtDl) -> None:
        with patch.object(
            YtDl,
            "_extract_info",
            side_effect=yt_dlp.utils.DownloadError("Something else went wrong"),
        ):
            with pytest.raises(YtDlError):
                await ytdl.get_video_info("abc123")


# ---------------------------------------------------------------------------
# get_video_formats tests
# ---------------------------------------------------------------------------


class TestGetVideoFormats:
    """Tests for YtDl.get_video_formats."""

    @pytest.mark.asyncio
    async def test_returns_formats(self, ytdl: YtDl) -> None:
        info = {
            "id": "abc123",
            "formats": [
                {
                    "format_id": "140",
                    "ext": "m4a",
                    "resolution": "audio only",
                    "acodec": "mp4a.40.2",
                    "abr": 129.5,
                    "asr": 44100,
                    "audio_channels": 2,
                    "tbr": 129.5,
                    "protocol": "https",
                    "format_note": "medium",
                    "format": "140 - audio only (medium)",
                },
                {
                    "format_id": "137",
                    "ext": "mp4",
                    "resolution": "1920x1080",
                    "fps": 30.0,
                    "vcodec": "avc1.640028",
                    "vbr": 4500.1,
                    "acodec": "none",
                    "tbr": 4500.1,
                    "protocol": "https",
                    "format_note": "1080p",
                    "format": "137 - 1920x1080 (1080p)",
                },
            ],
        }
        with patch.object(YtDl, "_extract_info", return_value=info):
            formats = await ytdl.get_video_formats("abc123")

        assert len(formats) == 2
        assert formats[0].format_id == "140"
        assert formats[0].ext == "m4a"
        assert formats[0].audio_channels == 2
        assert formats[0].abr == 129.5
        assert formats[1].format_id == "137"
        assert formats[1].resolution == "1920x1080"
        assert formats[1].fps == 30.0

    @pytest.mark.asyncio
    async def test_url_contains_encoded_video_id(self, ytdl: YtDl) -> None:
        captured_url: str = ""

        def capture_extract(url: str, opts: dict | None = None) -> dict:
            nonlocal captured_url
            captured_url = url
            return {"id": "abc123", "formats": []}

        with patch.object(YtDl, "_extract_info", side_effect=capture_extract):
            await ytdl.get_video_formats("abc123")

        assert captured_url.startswith("https://www.youtube.com/watch?v=")
        assert "abc123" in captured_url

    @pytest.mark.asyncio
    async def test_passes_ignore_no_formats_error(self, ytdl: YtDl) -> None:
        """yt-dlp's default selector raises if no format matches; we only
        want the list, so the call must opt out of that error."""
        captured_opts: dict = {}

        def capture_extract(url: str, opts: dict | None = None) -> dict:
            captured_opts.update(opts or {})
            return {"formats": []}

        with patch.object(YtDl, "_extract_info", side_effect=capture_extract):
            await ytdl.get_video_formats("abc123")

        assert captured_opts.get("ignore_no_formats_error") is True

    @pytest.mark.asyncio
    async def test_missing_formats_key_yields_empty_list(self, ytdl: YtDl) -> None:
        with patch.object(YtDl, "_extract_info", return_value={"id": "abc"}):
            formats = await ytdl.get_video_formats("abc")

        assert formats == []

    @pytest.mark.asyncio
    async def test_null_formats_yields_empty_list(self, ytdl: YtDl) -> None:
        """yt-dlp can emit ``formats: None`` for some extractor edge cases."""
        with patch.object(
            YtDl, "_extract_info", return_value={"id": "abc", "formats": None}
        ):
            formats = await ytdl.get_video_formats("abc")

        assert formats == []

    @pytest.mark.asyncio
    async def test_format_with_only_required_fields(self, ytdl: YtDl) -> None:
        """Formats often omit optional fields; the model must tolerate that."""
        info = {"formats": [{"format_id": "18", "ext": "mp4"}]}
        with patch.object(YtDl, "_extract_info", return_value=info):
            formats = await ytdl.get_video_formats("abc")

        assert len(formats) == 1
        assert formats[0].format_id == "18"
        assert formats[0].ext == "mp4"
        assert formats[0].resolution is None
        assert formats[0].fps is None

    @pytest.mark.asyncio
    async def test_raises_item_not_found_on_404(self, ytdl: YtDl) -> None:
        with patch.object(
            YtDl,
            "_extract_info",
            side_effect=yt_dlp.utils.DownloadError("Video unavailable"),
        ):
            with pytest.raises(ItemNotFoundError):
                await ytdl.get_video_formats("abc123")

    @pytest.mark.asyncio
    async def test_raises_auth_error_on_signin_required(self, ytdl: YtDl) -> None:
        with patch.object(
            YtDl,
            "_extract_info",
            side_effect=yt_dlp.utils.DownloadError(
                "Sign in to confirm you're not a bot"
            ),
        ):
            with pytest.raises(YtDlAuthError):
                await ytdl.get_video_formats("abc123")

    @pytest.mark.asyncio
    async def test_raises_ytdl_error_on_other_download_error(self, ytdl: YtDl) -> None:
        with patch.object(
            YtDl,
            "_extract_info",
            side_effect=yt_dlp.utils.DownloadError("Some other error"),
        ):
            with pytest.raises(YtDlError):
                await ytdl.get_video_formats("abc123")


# ---------------------------------------------------------------------------
# download_audio tests
# ---------------------------------------------------------------------------


class TestDownloadAudio:
    """Tests for YtDl.download_audio."""

    @pytest.mark.asyncio
    async def test_calls_ydl_download(self, ytdl: YtDl) -> None:
        mock_ydl = MagicMock()
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)
        mock_ydl.download = MagicMock()

        with patch("app.ytdl.yt_dlp.YoutubeDL", return_value=mock_ydl):
            await ytdl.download_audio("abc123", Path("/tmp/out.m4a"))

        mock_ydl.download.assert_called_once()
        url_arg = mock_ydl.download.call_args[0][0]
        assert "abc123" in url_arg[0]

    @pytest.mark.asyncio
    async def test_default_sponsorblock_categories(self, ytdl: YtDl) -> None:
        captured_opts: dict = {}

        def capture_ydl(opts: dict) -> MagicMock:
            captured_opts.update(opts)
            mock = MagicMock()
            mock.__enter__ = MagicMock(return_value=mock)
            mock.__exit__ = MagicMock(return_value=False)
            return mock

        with patch("app.ytdl.yt_dlp.YoutubeDL", side_effect=capture_ydl):
            await ytdl.download_audio("vid1", Path("/tmp/out.m4a"))

        postprocessors = captured_opts["postprocessors"]
        sb_pp = next(p for p in postprocessors if p["key"] == "SponsorBlock")
        assert sb_pp["categories"] == ["sponsor", "selfpromo"]

    @pytest.mark.asyncio
    async def test_custom_sponsorblock_categories(self, ytdl: YtDl) -> None:
        captured_opts: dict = {}

        def capture_ydl(opts: dict) -> MagicMock:
            captured_opts.update(opts)
            mock = MagicMock()
            mock.__enter__ = MagicMock(return_value=mock)
            mock.__exit__ = MagicMock(return_value=False)
            return mock

        with patch("app.ytdl.yt_dlp.YoutubeDL", side_effect=capture_ydl):
            await ytdl.download_audio(
                "vid1",
                Path("/tmp/out.m4a"),
                sponsorblock_categories=["intro", "outro"],
            )

        postprocessors = captured_opts["postprocessors"]
        sb_pp = next(p for p in postprocessors if p["key"] == "SponsorBlock")
        assert sb_pp["categories"] == ["intro", "outro"]

    @pytest.mark.asyncio
    async def test_output_path_in_opts(self, ytdl: YtDl) -> None:
        captured_opts: dict = {}

        def capture_ydl(opts: dict) -> MagicMock:
            captured_opts.update(opts)
            mock = MagicMock()
            mock.__enter__ = MagicMock(return_value=mock)
            mock.__exit__ = MagicMock(return_value=False)
            return mock

        with patch("app.ytdl.yt_dlp.YoutubeDL", side_effect=capture_ydl):
            await ytdl.download_audio("vid1", Path("/tmp/my_audio.m4a"))

        assert captured_opts["outtmpl"] == "/tmp/my_audio.m4a"

    @pytest.mark.asyncio
    async def test_raises_item_not_found_on_unavailable_video(self, ytdl: YtDl) -> None:
        mock_ydl = MagicMock()
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)
        mock_ydl.download.side_effect = yt_dlp.utils.DownloadError("Video unavailable")

        with patch("app.ytdl.yt_dlp.YoutubeDL", return_value=mock_ydl):
            with pytest.raises(ItemNotFoundError, match="Video not found"):
                await ytdl.download_audio("gone", Path("/tmp/out.m4a"))

    @pytest.mark.asyncio
    async def test_raises_ytdl_error_on_other_download_error(self, ytdl: YtDl) -> None:
        mock_ydl = MagicMock()
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)
        mock_ydl.download.side_effect = yt_dlp.utils.DownloadError("Some other error")

        with patch("app.ytdl.yt_dlp.YoutubeDL", return_value=mock_ydl):
            with pytest.raises(YtDlError, match="Some other error"):
                await ytdl.download_audio("vid1", Path("/tmp/out.m4a"))

    @pytest.mark.asyncio
    async def test_url_contains_encoded_video_id(self, ytdl: YtDl) -> None:
        captured_urls: list[str] = []

        mock_ydl = MagicMock()
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)

        def capture_download(urls: list[str]) -> None:
            captured_urls.extend(urls)

        mock_ydl.download = capture_download

        with patch("app.ytdl.yt_dlp.YoutubeDL", return_value=mock_ydl):
            await ytdl.download_audio("abc_123", Path("/tmp/out.m4a"))

        assert len(captured_urls) == 1
        assert "abc_123" in captured_urls[0]
        assert captured_urls[0].startswith("https://www.youtube.com/watch?v=")


# ---------------------------------------------------------------------------
# _is_not_found helper tests
# ---------------------------------------------------------------------------


class TestIsNotFound:
    """Tests for the static _is_not_found helper."""

    def test_404_detected(self) -> None:
        exc = yt_dlp.utils.DownloadError("HTTP Error 404: Not Found")
        assert YtDl._is_not_found(exc) is True

    def test_not_found_phrase_detected(self) -> None:
        exc = yt_dlp.utils.DownloadError("Channel not found")
        assert YtDl._is_not_found(exc) is True

    def test_does_not_exist_detected(self) -> None:
        exc = yt_dlp.utils.DownloadError("The page does not exist")
        assert YtDl._is_not_found(exc) is True

    def test_server_error_not_matched(self) -> None:
        exc = yt_dlp.utils.DownloadError("HTTP Error 500: Internal Server Error")
        assert YtDl._is_not_found(exc) is False

    def test_video_unavailable_detected(self) -> None:
        exc = yt_dlp.utils.DownloadError("Video unavailable")
        assert YtDl._is_not_found(exc) is True

    def test_generic_error_not_matched(self) -> None:
        exc = yt_dlp.utils.DownloadError("Something went wrong")
        assert YtDl._is_not_found(exc) is False


# ---------------------------------------------------------------------------
# _is_auth_required helper tests
# ---------------------------------------------------------------------------


class TestIsAuthRequired:
    """Tests for the static _is_auth_required helper."""

    def test_sign_in_to_confirm_detected(self) -> None:
        exc = yt_dlp.utils.DownloadError(
            "ERROR: [youtube] foo: Sign in to confirm you're not a bot."
        )
        assert YtDl._is_auth_required(exc) is True

    def test_use_cookies_hint_detected(self) -> None:
        exc = yt_dlp.utils.DownloadError("Use --cookies-from-browser or --cookies")
        assert YtDl._is_auth_required(exc) is True

    def test_unrelated_error_not_matched(self) -> None:
        exc = yt_dlp.utils.DownloadError("HTTP Error 500: Server Error")
        assert YtDl._is_auth_required(exc) is False

    def test_not_found_not_matched(self) -> None:
        exc = yt_dlp.utils.DownloadError("HTTP Error 404: Not Found")
        assert YtDl._is_auth_required(exc) is False


# ---------------------------------------------------------------------------
# Auth-error propagation tests — auth errors must take precedence over the
# not-found path so the worker can fire its alert.
# ---------------------------------------------------------------------------


class TestAuthErrorPropagation:
    """Tests that auth-required errors surface as YtDlAuthError everywhere."""

    @pytest.mark.asyncio
    async def test_get_video_info_raises_auth_error(self, ytdl: YtDl) -> None:
        with patch.object(
            YtDl,
            "_extract_info",
            side_effect=yt_dlp.utils.DownloadError(
                "Sign in to confirm you're not a bot"
            ),
        ):
            with pytest.raises(YtDlAuthError):
                await ytdl.get_video_info("abc123")

    @pytest.mark.asyncio
    async def test_get_channel_info_raises_auth_error(self, ytdl: YtDl) -> None:
        """Auth gate hits on the very first URL probe — must NOT fall through
        to the next pattern; we want a single alert, not silent retries."""
        with patch.object(
            YtDl,
            "_extract_info",
            side_effect=yt_dlp.utils.DownloadError(
                "Sign in to confirm you're not a bot"
            ),
        ):
            with pytest.raises(YtDlAuthError):
                await ytdl.get_channel_info("Techmoan")

    @pytest.mark.asyncio
    async def test_download_audio_raises_auth_error(self, ytdl: YtDl) -> None:
        mock_ydl = MagicMock()
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)
        mock_ydl.download.side_effect = yt_dlp.utils.DownloadError(
            "Sign in to confirm you're not a bot"
        )

        with patch("app.ytdl.yt_dlp.YoutubeDL", return_value=mock_ydl):
            with pytest.raises(YtDlAuthError):
                await ytdl.download_audio("vid1", Path("/tmp/out.m4a"))


# ---------------------------------------------------------------------------
# Cookie wiring tests
# ---------------------------------------------------------------------------


class TestCookies:
    """Tests that cookies_path is plumbed into yt-dlp opts when present."""

    @pytest.mark.asyncio
    async def test_cookies_added_to_download_opts_when_file_exists(
        self, tmp_path: Path
    ) -> None:
        cookies_file = tmp_path / "cookies.txt"
        cookies_file.write_text("# Netscape HTTP Cookie File\n")
        ytdl = YtDl(cookies_path=cookies_file)

        captured_opts: dict = {}

        def capture_ydl(opts: dict) -> MagicMock:
            captured_opts.update(opts)
            mock = MagicMock()
            mock.__enter__ = MagicMock(return_value=mock)
            mock.__exit__ = MagicMock(return_value=False)
            return mock

        with patch("app.ytdl.yt_dlp.YoutubeDL", side_effect=capture_ydl):
            await ytdl.download_audio("vid1", Path("/tmp/out.m4a"))

        cookiefile = captured_opts.get("cookiefile")
        assert cookiefile is not None
        # Should be a writable copy, not the (possibly read-only) source.
        assert cookiefile != str(cookies_file)
        assert Path(cookiefile).read_text() == "# Netscape HTTP Cookie File\n"

    def test_cookies_source_is_copied_to_writable_location(
        self, tmp_path: Path
    ) -> None:
        """The source cookies file may sit on a read-only mount; the copy
        yt-dlp uses must be writable so its post-extract jar save succeeds."""
        cookies_file = tmp_path / "cookies.txt"
        cookies_file.write_text("# Netscape HTTP Cookie File\n")
        # Make the source dir read-only to simulate the Cloud Run secret mount.
        cookies_file.chmod(0o444)
        ytdl = YtDl(cookies_path=cookies_file)

        copy_path = ytdl._cookies_path
        assert copy_path is not None
        assert copy_path != cookies_file
        assert os.access(copy_path, os.W_OK)
        # Writing back to the copy must succeed (this is what yt-dlp does
        # on YoutubeDL.__exit__).
        copy_path.write_text("# rewritten\n")
        assert copy_path.read_text() == "# rewritten\n"

    @pytest.mark.asyncio
    async def test_missing_cookies_file_is_silently_ignored(
        self, tmp_path: Path
    ) -> None:
        """Local dev (no secret mounted) must not blow up — yt-dlp opts
        should simply omit cookiefile when the configured path doesn't
        exist."""
        ytdl = YtDl(cookies_path=tmp_path / "does_not_exist.txt")

        captured_opts: dict = {}

        def capture_ydl(opts: dict) -> MagicMock:
            captured_opts.update(opts)
            mock = MagicMock()
            mock.__enter__ = MagicMock(return_value=mock)
            mock.__exit__ = MagicMock(return_value=False)
            return mock

        with patch("app.ytdl.yt_dlp.YoutubeDL", side_effect=capture_ydl):
            await ytdl.download_audio("vid1", Path("/tmp/out.m4a"))

        assert "cookiefile" not in captured_opts
