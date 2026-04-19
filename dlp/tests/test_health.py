"""Tests for the health check endpoint."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.dependencies import get_settings
from app.main import app


def override_get_settings() -> Settings:
    """Return a test settings instance."""
    return Settings(app_name="test-app", debug=True)


app.dependency_overrides[get_settings] = override_get_settings


@pytest.mark.asyncio
async def test_health_check() -> None:
    """Assert the health endpoint returns 200 and status ok."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
