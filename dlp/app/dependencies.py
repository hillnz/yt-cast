"""FastAPI dependency functions."""

from functools import lru_cache
from pathlib import Path

from fastapi import Depends, HTTPException, Request, status

from app.config import Settings, settings
from app.gdrive import GDrive
from app.storage import LocalStorage, Storage
from app.ytdl import YtDl


def get_settings() -> Settings:
    """Return the application settings singleton."""
    return settings


@lru_cache(maxsize=1)
def get_ytdl() -> YtDl:
    """Return a cached YtDl service instance."""
    return YtDl()


@lru_cache(maxsize=1)
def get_storage() -> Storage:
    """Return a cached Storage instance based on configuration.

    The backend is selected via the ``STORAGE_BACKEND`` setting:
    ``"local"`` uses :class:`LocalStorage`, ``"gdrive"`` (default) uses
    :class:`GDrive`.
    """
    s = get_settings()
    if s.storage_backend == "local":
        return LocalStorage(path_prefix=s.local_storage_path)
    return GDrive(
        credentials_path=Path(s.credentials_path),
        path_prefix=s.drive_folder,
    )


async def verify_bearer_token(
    request: Request,
    s: Settings = Depends(get_settings),
) -> None:
    """Check the Authorization header when a bearer token is configured.

    If ``BEARER_TOKEN`` is not set, all requests are allowed through.
    When it *is* set, every request must include a valid
    ``Authorization: Bearer <token>`` header.
    """
    if not s.bearer_token:
        return

    auth_header = request.headers.get("Authorization")
    if auth_header is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or token != s.bearer_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
