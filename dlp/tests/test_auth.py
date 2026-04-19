"""Tests for bearer token authentication."""

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.dependencies import get_settings, get_storage, get_ytdl
from app.main import app
from app.storage import Storage
from app.ytdl import Channel, Video, YtDl

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
def override_service_deps(mock_ytdl: AsyncMock, mock_storage: AsyncMock):
    """Override the YtDl and Storage dependencies with mocks."""
    app.dependency_overrides[get_ytdl] = lambda: mock_ytdl
    app.dependency_overrides[get_storage] = lambda: mock_storage
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def no_token(override_service_deps):
    """Configure the app with no bearer token (auth disabled)."""
    app.dependency_overrides[get_settings] = lambda: Settings(bearer_token=None)
    yield
    if get_settings in app.dependency_overrides:
        del app.dependency_overrides[get_settings]


@pytest.fixture
def with_token(override_service_deps):
    """Configure the app with a bearer token (auth enabled)."""
    app.dependency_overrides[get_settings] = lambda: Settings(bearer_token="secret123")
    yield
    if get_settings in app.dependency_overrides:
        del app.dependency_overrides[get_settings]


@pytest.fixture
def empty_token(override_service_deps):
    """Configure the app with an empty-string bearer token (auth disabled)."""
    app.dependency_overrides[get_settings] = lambda: Settings(bearer_token="")
    yield
    if get_settings in app.dependency_overrides:
        del app.dependency_overrides[get_settings]


@pytest.fixture
def sample_video() -> Video:
    """Return a sample Video model."""
    return Video(
        id="abc123",
        title="Test Video",
        description="A test video.",
        upload_date="20240101",
        duration="5:00",
    )


@pytest.fixture
def sample_channel() -> Channel:
    """Return a sample Channel model."""
    return Channel(
        channel="TestChannel",
        description="A test channel",
        thumbnails=[],
        webpage_url="https://www.youtube.com/@TestChannel/about",
        videos_url="https://www.youtube.com/@TestChannel/videos",
        epoch=1700000000,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def request_with_auth(
    method: str,
    url: str,
    token: str | None = None,
    json: dict | None = None,
) -> tuple[int, dict | bytes]:
    """Make a request optionally including a Bearer token and return status + body."""
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.request(method, url, headers=headers, json=json)

    try:
        return response.status_code, response.json()
    except Exception:
        return response.status_code, response.content


# ---------------------------------------------------------------------------
# No token configured — all requests should pass through
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_token_health_passes(no_token) -> None:
    """Health endpoint should be accessible when no bearer token is configured."""
    status, body = await request_with_auth("GET", "/health")
    assert status == 200


@pytest.mark.asyncio
async def test_no_token_video_passes(
    no_token, mock_ytdl: AsyncMock, sample_video: Video
) -> None:
    """Video endpoint should be accessible when no bearer token is configured."""
    mock_ytdl.get_video_info.return_value = sample_video
    status, body = await request_with_auth("GET", "/video/abc123")
    assert status == 200


@pytest.mark.asyncio
async def test_no_token_channel_passes(
    no_token, mock_ytdl: AsyncMock, sample_channel: Channel
) -> None:
    """Channel endpoint should be accessible when no bearer token is configured."""
    mock_ytdl.get_channel_info.return_value = sample_channel
    mock_ytdl.get_channel_videos.return_value = ["vid1"]
    status, body = await request_with_auth("GET", "/channel/TestChannel")
    assert status == 200


@pytest.mark.asyncio
async def test_no_token_download_passes(no_token, mock_ytdl: AsyncMock) -> None:
    """Download endpoint should be accessible when no bearer token is configured."""
    status, body = await request_with_auth(
        "POST", "/download", json={"video_id": "abc123"}
    )
    assert status == 204


# ---------------------------------------------------------------------------
# Empty-string token — should behave like no token (auth disabled)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_token_health_passes(empty_token) -> None:
    """Health endpoint should be accessible when bearer token is an empty string."""
    status, body = await request_with_auth("GET", "/health")
    assert status == 200


# ---------------------------------------------------------------------------
# Token configured — missing Authorization header
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_with_token_health_missing_header(with_token) -> None:
    """Health endpoint should return 401 when bearer token is set but no Authorization header is sent."""
    status, body = await request_with_auth("GET", "/health")
    assert status == 401
    assert "Missing Authorization header" in body["detail"]


@pytest.mark.asyncio
async def test_with_token_video_missing_header(with_token) -> None:
    """Video endpoint should return 401 when bearer token is set but no Authorization header is sent."""
    status, body = await request_with_auth("GET", "/video/abc123")
    assert status == 401


@pytest.mark.asyncio
async def test_with_token_channel_missing_header(with_token) -> None:
    """Channel endpoint should return 401 when bearer token is set but no Authorization header is sent."""
    status, body = await request_with_auth("GET", "/channel/TestChannel")
    assert status == 401


@pytest.mark.asyncio
async def test_with_token_download_missing_header(with_token) -> None:
    """Download endpoint should return 401 when bearer token is set but no Authorization header is sent."""
    status, body = await request_with_auth(
        "POST", "/download", json={"video_id": "abc123"}
    )
    assert status == 401


# ---------------------------------------------------------------------------
# Token configured — wrong token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_with_token_health_wrong_token(with_token) -> None:
    """Health endpoint should return 401 with an incorrect bearer token."""
    status, body = await request_with_auth("GET", "/health", token="wrong")
    assert status == 401
    assert "Invalid bearer token" in body["detail"]


@pytest.mark.asyncio
async def test_with_token_download_wrong_token(with_token) -> None:
    """Download endpoint should return 401 with an incorrect bearer token."""
    status, body = await request_with_auth(
        "POST", "/download", token="wrong", json={"video_id": "abc123"}
    )
    assert status == 401


# ---------------------------------------------------------------------------
# Token configured — wrong scheme
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_with_token_wrong_scheme(with_token) -> None:
    """Using a non-Bearer scheme should return 401."""
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/health",
            headers={"Authorization": "Basic secret123"},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_with_token_bearer_prefix_only(with_token) -> None:
    """Sending 'Bearer ' with no token value should return 401."""
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/health",
            headers={"Authorization": "Bearer"},
        )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Token configured — correct token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_with_token_health_correct_token(with_token) -> None:
    """Health endpoint should return 200 with the correct bearer token."""
    status, body = await request_with_auth("GET", "/health", token="secret123")
    assert status == 200


@pytest.mark.asyncio
async def test_with_token_video_correct_token(
    with_token, mock_ytdl: AsyncMock, sample_video: Video
) -> None:
    """Video endpoint should return 200 with the correct bearer token."""
    mock_ytdl.get_video_info.return_value = sample_video
    status, body = await request_with_auth("GET", "/video/abc123", token="secret123")
    assert status == 200


@pytest.mark.asyncio
async def test_with_token_channel_correct_token(
    with_token, mock_ytdl: AsyncMock, sample_channel: Channel
) -> None:
    """Channel endpoint should return 200 with the correct bearer token."""
    mock_ytdl.get_channel_info.return_value = sample_channel
    mock_ytdl.get_channel_videos.return_value = ["vid1"]
    status, body = await request_with_auth(
        "GET", "/channel/TestChannel", token="secret123"
    )
    assert status == 200


@pytest.mark.asyncio
async def test_with_token_download_correct_token(
    with_token, mock_ytdl: AsyncMock
) -> None:
    """Download endpoint should return 204 with the correct bearer token."""
    status, body = await request_with_auth(
        "POST", "/download", token="secret123", json={"video_id": "abc123"}
    )
    assert status == 204


# ---------------------------------------------------------------------------
# Token configured — case-insensitive Bearer scheme
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_with_token_lowercase_bearer_scheme(with_token) -> None:
    """The 'bearer' scheme (lowercase) should also be accepted."""
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/health",
            headers={"Authorization": "bearer secret123"},
        )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Token configured — WWW-Authenticate header on 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_with_token_www_authenticate_header(with_token) -> None:
    """401 responses should include a WWW-Authenticate: Bearer header."""
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get("/health")
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"


@pytest.mark.asyncio
async def test_with_token_www_authenticate_header_wrong_token(with_token) -> None:
    """401 responses for wrong token should also include WWW-Authenticate: Bearer header."""
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/health",
            headers={"Authorization": "Bearer wrong"},
        )
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"
