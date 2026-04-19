"""Storage interface and implementations for saving files."""

import abc
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class StorageError(Exception):
    """Base error for storage operations."""


# ---------------------------------------------------------------------------
# Storage interface
# ---------------------------------------------------------------------------


class Storage(abc.ABC):
    """Abstract interface for saving files to a storage backend.

    Implementations must support a configurable path prefix and a key-based
    save operation.  Files are stored at ``prefix / key / filename``.
    """

    @abc.abstractmethod
    async def save_file(self, local_path: Path | str, key: str) -> str:
        """Save a local file to the storage backend.

        The file is saved under the path ``prefix / key``.  The stored
        filename matches the local filename.

        Parameters
        ----------
        local_path:
            Path to the local file to save.
        key:
            Key used to construct the storage path (appended to
            the configured prefix).  Use ``/``-separated segments to
            create nested paths, e.g. ``"videos/abc123"``.

        Returns
        -------
        str
            A backend-specific identifier for the saved file.

        Raises
        ------
        FileNotFoundError
            If the local file does not exist.
        StorageError
            If the save operation fails.
        """
        ...


# ---------------------------------------------------------------------------
# Local filesystem implementation
# ---------------------------------------------------------------------------


class LocalStorage(Storage):
    """Save files to the local filesystem.

    Files are saved to ``path_prefix / key / filename``.  Directories
    are created automatically.
    """

    def __init__(self, path_prefix: str) -> None:
        self._path_prefix = path_prefix

    async def save_file(self, local_path: Path | str, key: str) -> str:
        """Copy a local file into the storage directory.

        Returns the destination path as a string.
        """
        local_path = Path(local_path)
        if not local_path.is_file():
            raise FileNotFoundError(f"Local file not found: {local_path}")

        dest_dir = Path(self._path_prefix) / key if key else Path(self._path_prefix)
        dest_path = dest_dir / local_path.name

        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(local_path, dest_path)
        except Exception as exc:
            raise StorageError(f"Failed to save {local_path}: {exc}") from exc

        logger.info("Saved %s -> %s", local_path, dest_path)
        return str(dest_path)
