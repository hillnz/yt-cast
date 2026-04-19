"""Health check router."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.config import Settings
from app.dependencies import get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Response model for the health check endpoint."""

    status: str
    version: str


@router.get("/health", response_model=HealthResponse)
async def health_check(settings: Settings = Depends(get_settings)) -> HealthResponse:
    """Return the current health status of the application."""
    return HealthResponse(status="ok", version="0.1.0")
