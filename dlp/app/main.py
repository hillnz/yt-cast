"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.routers import channel, download, health, video
from app.storage import StorageError
from app.ytdl import ItemNotFoundError, YtDlAuthError, YtDlError


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown events."""
    # Startup: initialise resources here as needed
    yield
    # Shutdown: clean up resources here as needed


app = FastAPI(
    title=settings.app_name,
    description="Archive API for the DLP project.",
    version="0.1.0",
    lifespan=lifespan,
    redoc_url="/redoc" if settings.redoc_enabled else None,
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return a generic 400 without leaking payload field details."""
    return JSONResponse(status_code=400, content={"detail": "Bad request"})


@app.exception_handler(ItemNotFoundError)
async def item_not_found_handler(
    request: Request, exc: ItemNotFoundError
) -> JSONResponse:
    """Return 404 when a YouTube item is not found."""
    return JSONResponse(status_code=404, content={"detail": "Not found"})


@app.exception_handler(YtDlAuthError)
async def ytdl_auth_error_handler(request: Request, exc: YtDlAuthError) -> JSONResponse:
    """Return a discriminated 502 when YouTube demands authentication.

    The ``code`` field lets the dlp-worker react specifically (e.g. fire
    an email alert prompting a cookie refresh) without parsing free-form
    detail strings.
    """
    return JSONResponse(
        status_code=502,
        content={
            "detail": "YouTube authentication required",
            "code": "youtube_auth_required",
        },
    )


@app.exception_handler(YtDlError)
async def ytdl_error_handler(request: Request, exc: YtDlError) -> JSONResponse:
    """Return 502 when yt-dlp encounters an error."""
    return JSONResponse(status_code=502, content={"detail": "Upstream error"})


@app.exception_handler(StorageError)
async def storage_error_handler(request: Request, exc: StorageError) -> JSONResponse:
    """Return 502 when the storage backend encounters an error."""
    return JSONResponse(status_code=502, content={"detail": "Upstream error"})


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(download.router)
app.include_router(channel.router)
app.include_router(video.router)
