"""FastAPI dependency functions."""

from functools import lru_cache
from pathlib import Path

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
    s = get_settings()
    cookies_path = Path(s.yt_cookies_path) if s.yt_cookies_path else None
    return YtDl(cookies_path=cookies_path, proxy=s.ytdl_proxy)


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
