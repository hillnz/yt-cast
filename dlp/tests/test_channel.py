"""Tests for the channel endpoint."""

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_ytdl
from app.gdrive import GDrive
from app.main import app
from app.ytdl import Channel, ItemNotFoundError, Thumbnail, YtDl, YtDlError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_ytdl() -> AsyncMock:
    """Return a mock YtDl instance."""
    return AsyncMock(spec=YtDl)


@pytest.fixture
def mock_gdrive() -> AsyncMock:
    """Return a mock GDrive instance (unused by channel but needed for app)."""
    return AsyncMock(spec=GDrive)


@pytest.fixture
def sample_channel() -> Channel:
    """Return a sample Channel model."""
    return Channel(
        channel="TestChannel",
        description="A test channel",
        thumbnails=[
            Thumbnail(url="https://example.com/thumb.jpg", width=100, height=100),
        ],
        webpage_url="https://www.youtube.com/@TestChannel/about",
        videos_url="https://www.youtube.com/@TestChannel/videos",
        epoch=1700000000,
    )


@pytest.fixture
def override_deps(mock_ytdl: AsyncMock, mock_gdrive: AsyncMock):
    """Override the YtDl and GDrive dependencies with mocks."""
    app.dependency_overrides[get_ytdl] = lambda: mock_ytdl
    yield
    app.dependency_overrides.clear()


async def get_channel(channel_id: str) -> tuple[int, list]:
    """Fetch the channel videos endpoint and return status + parsed JSON."""
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get(f"/channel/{channel_id}")
    return response.status_code, response.json()


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_returns_video_ids(
    override_deps, mock_ytdl: AsyncMock, sample_channel: Channel
) -> None:
    """Should return a list of video IDs for a valid channel."""
    mock_ytdl.get_channel_info.return_value = sample_channel
    mock_ytdl.get_channel_videos.return_value = ["abc123", "def456"]

    status, body = await get_channel("TestChannel")

    assert status == 200
    assert body == ["abc123", "def456"]


@pytest.mark.asyncio
async def test_empty_video_list(
    override_deps, mock_ytdl: AsyncMock, sample_channel: Channel
) -> None:
    """Should return an empty list when the channel has no recent videos."""
    mock_ytdl.get_channel_info.return_value = sample_channel
    mock_ytdl.get_channel_videos.return_value = []

    status, body = await get_channel("TestChannel")

    assert status == 200
    assert body == []


@pytest.mark.asyncio
async def test_calls_get_channel_info_with_channel_id(
    override_deps, mock_ytdl: AsyncMock, sample_channel: Channel
) -> None:
    """get_channel_info should be called with the channel_id from the URL."""
    mock_ytdl.get_channel_info.return_value = sample_channel
    mock_ytdl.get_channel_videos.return_value = ["vid1"]

    await get_channel("MyChannel")

    mock_ytdl.get_channel_info.assert_awaited_once_with("MyChannel")


@pytest.mark.asyncio
async def test_calls_get_channel_videos_with_channel_info(
    override_deps, mock_ytdl: AsyncMock, sample_channel: Channel
) -> None:
    """get_channel_videos should be called with the Channel object returned by get_channel_info."""
    mock_ytdl.get_channel_info.return_value = sample_channel
    mock_ytdl.get_channel_videos.return_value = ["vid1"]

    await get_channel("MyChannel")

    mock_ytdl.get_channel_videos.assert_awaited_once_with(sample_channel)


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_item_not_found_returns_404(override_deps, mock_ytdl: AsyncMock) -> None:
    """ItemNotFoundError from ytdl should return 404."""
    mock_ytdl.get_channel_info.side_effect = ItemNotFoundError("not found")

    status, _ = await get_channel("NonExistentChannel")

    assert status == 404


@pytest.mark.asyncio
async def test_ytdl_error_returns_502(override_deps, mock_ytdl: AsyncMock) -> None:
    """YtDlError from ytdl should return 502."""
    mock_ytdl.get_channel_info.side_effect = YtDlError("extraction failed")

    status, _ = await get_channel("SomeChannel")

    assert status == 502
