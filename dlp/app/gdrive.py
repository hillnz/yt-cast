"""Google Drive upload functionality using google-api-python-client."""

import asyncio
import logging
import mimetypes
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from app.storage import Storage, StorageError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Scope required for Drive file access.
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class GDriveError(StorageError):
    """Base error for Google Drive operations."""


class FolderNotFoundError(GDriveError):
    """Raised when a Drive folder cannot be found or created."""


class UploadError(GDriveError):
    """Raised when a file upload to Drive fails."""


# ---------------------------------------------------------------------------
# GDrive service
# ---------------------------------------------------------------------------


class GDrive(Storage):
    """Wrapper around the Google Drive SDK for uploading files.

    Files are uploaded to a folder hierarchy rooted at :data:`PATH_PREFIX`.
    The remote path is constructed as ``PATH_PREFIX / key`` where *key* is
    provided by the caller.  The uploaded file retains its local filename.

    Authentication uses a Google service account.  Set the
    ``GOOGLE_APPLICATION_CREDENTIALS`` environment variable or pass the path
    explicitly via *credentials_path*.
    """

    def __init__(
        self,
        credentials_path: Path,
        path_prefix: str,
    ) -> None:
        self._credentials_path = Path(credentials_path)
        self._path_prefix = path_prefix
        self._service = None

    # -- Internal helpers ---------------------------------------------------

    def _get_service(self):
        """Lazily build and cache the Drive service client."""
        if self._service is None:
            creds = service_account.Credentials.from_service_account_file(
                str(self._credentials_path),
                scopes=DRIVE_SCOPES,
            )
            self._service = build("drive", "v3", credentials=creds)
        return self._service

    def _ensure_folder(self, folder_path: str) -> str:
        """Ensure a folder hierarchy exists in Drive, creating it if needed.

        Parameters
        ----------
        folder_path:
            Slash-separated path, e.g. ``"dlp-archive/videos/abc123"``.

        Returns
        -------
        str
            The Google Drive folder ID of the deepest folder.
        """
        service = self._get_service()
        parts = [p for p in folder_path.split("/") if p]
        parent_id = "root"

        for part in parts:
            query = (
                f"name='{part}' and "
                f"'{parent_id}' in parents and "
                f"mimeType='application/vnd.google-apps.folder' and "
                f"trashed=false"
            )
            response = (
                service.files()
                .list(q=query, spaces="drive", fields="files(id, name)")
                .execute()
            )
            files = response.get("files", [])

            if files:
                parent_id = files[0]["id"]
            else:
                folder_metadata = {
                    "name": part,
                    "mimeType": "application/vnd.google-apps.folder",
                    "parents": [parent_id],
                }
                folder = (
                    service.files().create(body=folder_metadata, fields="id").execute()
                )
                parent_id = folder["id"]
                logger.info("Created folder: %s (id=%s)", part, parent_id)

        return parent_id

    def _upload_file(self, local_path: Path, key: str) -> str:
        """Synchronous upload implementation.

        Creates the target folder hierarchy (``path_prefix / key``), then
        uploads the local file into it.
        """
        service = self._get_service()

        # Build the remote folder path.
        remote_folder = f"{self._path_prefix}/{key}" if key else self._path_prefix
        parent_id = self._ensure_folder(remote_folder)

        # Determine MIME type.
        mime_type, _ = mimetypes.guess_type(str(local_path))
        if mime_type is None:
            mime_type = "application/octet-stream"

        media = MediaFileUpload(str(local_path), mimetype=mime_type, resumable=True)
        file_metadata = {
            "name": local_path.name,
            "parents": [parent_id],
        }

        try:
            file = (
                service.files()
                .create(
                    body=file_metadata,
                    media_body=media,
                    fields="id, name",
                )
                .execute()
            )
        except Exception as exc:
            raise UploadError(f"Failed to upload {local_path}: {exc}") from exc

        file_id = file["id"]
        logger.info(
            "Uploaded %s -> %s/%s (id=%s)",
            local_path,
            remote_folder,
            local_path.name,
            file_id,
        )
        return file_id

    # -- Public API ---------------------------------------------------------

    async def save_file(self, local_path: Path | str, key: str) -> str:
        """Upload a local file to Google Drive.

        The file is uploaded to the folder ``path_prefix / key``.  The remote
        filename matches the local filename.

        Parameters
        ----------
        local_path:
            Path to the local file to upload.
        key:
            Key used to construct the remote folder path (appended to
            the path prefix).  Use ``/``-separated segments to create
            nested folders, e.g. ``"videos/abc123"``.

        Returns
        -------
        str
            The Google Drive file ID of the uploaded file.

        Raises
        ------
        FileNotFoundError
            If the local file does not exist.
        GDriveError
            If the upload fails.
        """
        local_path = Path(local_path)
        if not local_path.is_file():
            raise FileNotFoundError(f"Local file not found: {local_path}")

        return await asyncio.to_thread(self._upload_file, local_path, key)
