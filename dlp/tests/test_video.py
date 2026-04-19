"""Tests for the video endpoint."""

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_ytdl
from app.gdrive import GDrive
from app.main import app
from app.ytdl import ItemNotFoundError, Video, YtDl, YtDlError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_ytdl() -> AsyncMock:
    """Return a mock YtDl instance."""
    return AsyncMock(spec=YtDl)


@pytest.fixture
def mock_gdrive() -> AsyncMock:
    """Return a mock GDrive instance (unused by video but needed for app)."""
    return AsyncMock(spec=GDrive)


@pytest.fixture
def sample_video() -> Video:
    """Return a sample Video model."""
    return Video(
        id="dQw4w9WgXcQ",
        title="Rick Astley - Never Gonna Give You Up",
        description='The official video for "Never Gonna Give You Up" by Rick Astley.',
        upload_date="20091025",
        duration="3:33",
    )


@pytest.fixture
def override_deps(mock_ytdl: AsyncMock, mock_gdrive: AsyncMock):
    """Override the YtDl and GDrive dependencies with mocks."""
    app.dependency_overrides[get_ytdl] = lambda: mock_ytdl
    yield
    app.dependency_overrides.clear()


async def get_video(video_id: str) -> tuple[int, dict]:
    """Fetch the video endpoint and return status + parsed JSON."""
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get(f"/video/{video_id}")
    return response.status_code, response.json()


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_returns_video_info(
    override_deps, mock_ytdl: AsyncMock, sample_video: Video
) -> None:
    """Should return video metadata for a valid video ID."""
    mock_ytdl.get_video_info.return_value = sample_video

    status, body = await get_video("dQw4w9WgXcQ")

    assert status == 200
    assert body["id"] == "dQw4w9WgXcQ"
    assert body["title"] == "Rick Astley - Never Gonna Give You Up"


@pytest.mark.asyncio
async def test_returns_all_video_fields(
    override_deps, mock_ytdl: AsyncMock, sample_video: Video
) -> None:
    """Should return all fields of the Video model."""
    mock_ytdl.get_video_info.return_value = sample_video

    status, body = await get_video("dQw4w9WgXcQ")

    assert status == 200
    assert body == {
        "id": "dQw4w9WgXcQ",
        "title": "Rick Astley - Never Gonna Give You Up",
        "description": 'The official video for "Never Gonna Give You Up" by Rick Astley.',
        "upload_date": "20091025",
        "duration": "3:33",
    }


@pytest.mark.asyncio
async def test_calls_get_video_info_with_video_id(
    override_deps, mock_ytdl: AsyncMock, sample_video: Video
) -> None:
    """get_video_info should be called with the video_id from the URL."""
    mock_ytdl.get_video_info.return_value = sample_video

    await get_video("abc123")

    mock_ytdl.get_video_info.assert_awaited_once_with("abc123")


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_item_not_found_returns_404(override_deps, mock_ytdl: AsyncMock) -> None:
    """ItemNotFoundError from ytdl should return 404."""
    mock_ytdl.get_video_info.side_effect = ItemNotFoundError("not found")

    status, _ = await get_video("NonExistentVideo")

    assert status == 404


@pytest.mark.asyncio
async def test_ytdl_error_returns_502(override_deps, mock_ytdl: AsyncMock) -> None:
    """YtDlError from ytdl should return 502."""
    mock_ytdl.get_video_info.side_effect = YtDlError("extraction failed")

    status, _ = await get_video("SomeVideo")

    assert status == 502
