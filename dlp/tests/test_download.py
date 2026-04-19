"""Tests for the download endpoint."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_storage, get_ytdl
from app.main import app
from app.storage import Storage, StorageError
from app.ytdl import ItemNotFoundError, YtDl, YtDlError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_ytdl() -> AsyncMock:
    """Return a mock YtDl instance."""
    return AsyncMock(spec=YtDl)


@pytest.fixture
def mock_storage() -> AsyncMock:
    """Return a mock Storage instance."""
    return AsyncMock(spec=Storage)


@pytest.fixture
def override_deps(mock_ytdl: AsyncMock, mock_storage: AsyncMock):
    """Override the YtDl and Storage dependencies with mocks."""
    app.dependency_overrides[get_ytdl] = lambda: mock_ytdl
    app.dependency_overrides[get_storage] = lambda: mock_storage
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def valid_payload() -> dict:
    """Return a minimal valid download request payload."""
    return {"video_id": "dQw4w9WgXcQ"}


async def post(payload: dict) -> tuple[int, bytes]:
    """Submit a payload to the download endpoint and return status + body."""
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.post("/download", json=payload)
    return response.status_code, response.content


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_minimal_valid_payload(
    valid_payload: dict, override_deps, mock_ytdl: AsyncMock, mock_storage: AsyncMock
) -> None:
    """A payload with only video_id should return 204."""
    status, body = await post(valid_payload)
    assert status == 204
    assert body == b""


@pytest.mark.asyncio
async def test_download_audio_called_with_video_id(
    valid_payload: dict, override_deps, mock_ytdl: AsyncMock, mock_storage: AsyncMock
) -> None:
    """download_audio should be called with the video_id."""
    await post(valid_payload)
    mock_ytdl.download_audio.assert_awaited_once()
    call_args = mock_ytdl.download_audio.call_args
    assert call_args[0][0] == "dQw4w9WgXcQ"


@pytest.mark.asyncio
async def test_download_audio_uses_m4a_extension(
    valid_payload: dict, override_deps, mock_ytdl: AsyncMock, mock_storage: AsyncMock
) -> None:
    """The temp file should use .m4a extension named after the video ID."""
    await post(valid_payload)
    call_args = mock_ytdl.download_audio.call_args
    output_path: Path = call_args[0][1]
    assert output_path.name == "dQw4w9WgXcQ.m4a"


@pytest.mark.asyncio
async def test_save_file_called_with_video_id_as_key(
    valid_payload: dict, override_deps, mock_ytdl: AsyncMock, mock_storage: AsyncMock
) -> None:
    """save_file should be called with the video_id as the key."""
    await post(valid_payload)
    mock_storage.save_file.assert_awaited_once()
    call_args = mock_storage.save_file.call_args
    assert call_args[1]["key"] == "dQw4w9WgXcQ"


@pytest.mark.asyncio
async def test_save_file_uses_output_path(
    valid_payload: dict, override_deps, mock_ytdl: AsyncMock, mock_storage: AsyncMock
) -> None:
    """save_file should be called with the same output path as download_audio."""
    await post(valid_payload)
    ytdl_path = mock_ytdl.download_audio.call_args[0][1]
    storage_path = mock_storage.save_file.call_args[0][0]
    assert storage_path == ytdl_path


# ---------------------------------------------------------------------------
# Error propagation tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_item_not_found_returns_404(
    valid_payload: dict, override_deps, mock_ytdl: AsyncMock
) -> None:
    """ItemNotFoundError from ytdl should return 404."""
    mock_ytdl.download_audio.side_effect = ItemNotFoundError("not found")
    status, _ = await post(valid_payload)
    assert status == 404


@pytest.mark.asyncio
async def test_ytdl_error_returns_502(
    valid_payload: dict, override_deps, mock_ytdl: AsyncMock
) -> None:
    """YtDlError from ytdl should return 502."""
    mock_ytdl.download_audio.side_effect = YtDlError("download failed")
    status, _ = await post(valid_payload)
    assert status == 502


@pytest.mark.asyncio
async def test_storage_error_returns_502(
    valid_payload: dict, override_deps, mock_storage: AsyncMock
) -> None:
    """StorageError from storage backend should return 502."""
    mock_storage.save_file.side_effect = StorageError("save failed")
    status, _ = await post(valid_payload)
    assert status == 502


@pytest.mark.asyncio
async def test_file_not_found_returns_500(
    valid_payload: dict, override_deps, mock_storage: AsyncMock
) -> None:
    """FileNotFoundError (local file missing) should return 500."""
    mock_storage.save_file.side_effect = FileNotFoundError("file not found")
    status, _ = await post(valid_payload)
    assert status == 500


# ---------------------------------------------------------------------------
# Rejection tests — 400 with no field detail leaked
# ---------------------------------------------------------------------------


async def assert_opaque_400(payload: dict) -> None:
    """Assert that the response is 400 and does not reveal field information."""
    status, body = await post(payload)
    assert status == 400
    decoded = body.decode()
    assert "video_id" not in decoded


@pytest.mark.asyncio
async def test_missing_video_id() -> None:
    """Omitting video_id should return an opaque 400."""
    await assert_opaque_400({})


@pytest.mark.asyncio
async def test_video_id_null() -> None:
    """Passing null for video_id should return an opaque 400."""
    await assert_opaque_400({"video_id": None})


@pytest.mark.asyncio
async def test_video_id_integer() -> None:
    """Passing an integer for video_id should return an opaque 400."""
    await assert_opaque_400({"video_id": 12345})


@pytest.mark.asyncio
async def test_extra_fields_are_ignored(valid_payload: dict, override_deps) -> None:
    """Unknown extra fields should not cause a failure."""
    valid_payload["extra_field"] = "surprise"
    status, _ = await post(valid_payload)
    assert status == 204
