"""Tests for the Storage interface and LocalStorage implementation."""

import os
from pathlib import Path

import pytest

from app.storage import LocalStorage, Storage, StorageError

# ---------------------------------------------------------------------------
# Storage ABC
# ---------------------------------------------------------------------------


class TestStorageABC:
    """Verify that Storage cannot be instantiated directly."""

    def test_cannot_instantiate_abc(self) -> None:
        """Storage is abstract and should raise TypeError on direct instantiation."""
        with pytest.raises(TypeError, match="abstract method"):
            Storage()  # type: ignore[abstract]

    def test_subclass_without_save_file_cannot_instantiate(self) -> None:
        """A subclass that doesn't implement save_file still can't be instantiated."""

        class IncompleteStorage(Storage):
            pass

        with pytest.raises(TypeError, match="abstract method"):
            IncompleteStorage()  # type: ignore[abstract]

    def test_subclass_with_save_file_can_instantiate(self) -> None:
        """A subclass that implements save_file can be instantiated."""

        class CompleteStorage(Storage):
            async def save_file(self, local_path: Path | str, key: str) -> str:
                return "ok"

        instance = CompleteStorage()
        assert isinstance(instance, Storage)


# ---------------------------------------------------------------------------
# StorageError
# ---------------------------------------------------------------------------


class TestStorageError:
    """Verify StorageError hierarchy."""

    def test_is_exception(self) -> None:
        """StorageError should be a subclass of Exception."""
        assert issubclass(StorageError, Exception)

    def test_can_raise_and_catch(self) -> None:
        """StorageError can be raised and caught."""
        with pytest.raises(StorageError, match="something failed"):
            raise StorageError("something failed")


# ---------------------------------------------------------------------------
# LocalStorage — constructor
# ---------------------------------------------------------------------------


class TestLocalStorageInit:
    """Test LocalStorage construction."""

    def test_is_storage(self) -> None:
        """LocalStorage should be a subclass of Storage."""
        assert issubclass(LocalStorage, Storage)

    def test_instance_check(self) -> None:
        """An instance of LocalStorage should pass isinstance checks for Storage."""
        store = LocalStorage(path_prefix="/tmp/test")
        assert isinstance(store, Storage)

    def test_stores_path_prefix(self, tmp_path: Path) -> None:
        """The path_prefix should be stored for later use."""
        store = LocalStorage(path_prefix=str(tmp_path))
        assert store._path_prefix == str(tmp_path)


# ---------------------------------------------------------------------------
# LocalStorage — save_file happy path
# ---------------------------------------------------------------------------


class TestLocalStorageSaveFile:
    """Test LocalStorage.save_file behaviour."""

    async def test_saves_file_to_prefix_key_dir(self, tmp_path: Path) -> None:
        """File should be copied to path_prefix/key/filename."""
        src = tmp_path / "source.txt"
        src.write_text("hello world")

        prefix = tmp_path / "archive"
        store = LocalStorage(path_prefix=str(prefix))

        result = await store.save_file(src, key="videos/abc123")

        expected = str(prefix / "videos" / "abc123" / "source.txt")
        assert result == expected
        assert Path(result).read_text() == "hello world"

    async def test_returns_destination_path(self, tmp_path: Path) -> None:
        """save_file should return the destination path as a string."""
        src = tmp_path / "data.bin"
        src.write_bytes(b"\x00\x01\x02")

        prefix = tmp_path / "out"
        store = LocalStorage(path_prefix=str(prefix))

        result = await store.save_file(src, key="item")

        assert isinstance(result, str)
        assert Path(result).is_file()

    async def test_creates_nested_directories(self, tmp_path: Path) -> None:
        """Intermediate directories should be created automatically."""
        src = tmp_path / "file.mp4"
        src.write_text("video content")

        prefix = tmp_path / "archive"
        store = LocalStorage(path_prefix=str(prefix))

        await store.save_file(src, key="deep/nested/path")

        dest = prefix / "deep" / "nested" / "path" / "file.mp4"
        assert dest.is_file()
        assert dest.read_text() == "video content"

    async def test_empty_key_saves_to_prefix_dir(self, tmp_path: Path) -> None:
        """With an empty key, the file should be saved directly in path_prefix."""
        src = tmp_path / "root.txt"
        src.write_text("root level")

        prefix = tmp_path / "archive"
        store = LocalStorage(path_prefix=str(prefix))

        result = await store.save_file(src, key="")

        expected = str(prefix / "root.txt")
        assert result == expected
        assert Path(result).read_text() == "root level"

    async def test_preserves_file_content_binary(self, tmp_path: Path) -> None:
        """Binary file content should be preserved exactly."""
        content = bytes(range(256))
        src = tmp_path / "binary.dat"
        src.write_bytes(content)

        prefix = tmp_path / "archive"
        store = LocalStorage(path_prefix=str(prefix))

        result = await store.save_file(src, key="bin")
        assert Path(result).read_bytes() == content

    async def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        """If the destination file already exists, it should be overwritten."""
        src = tmp_path / "doc.txt"
        src.write_text("new content")

        prefix = tmp_path / "archive"
        dest_dir = prefix / "key"
        dest_dir.mkdir(parents=True)
        existing = dest_dir / "doc.txt"
        existing.write_text("old content")

        store = LocalStorage(path_prefix=str(prefix))
        result = await store.save_file(src, key="key")

        assert Path(result).read_text() == "new content"

    async def test_accepts_string_local_path(self, tmp_path: Path) -> None:
        """save_file should accept a string path, not just Path."""
        src = tmp_path / "strpath.txt"
        src.write_text("string path")

        prefix = tmp_path / "archive"
        store = LocalStorage(path_prefix=str(prefix))

        result = await store.save_file(str(src), key="str")

        assert Path(result).read_text() == "string path"

    async def test_preserves_metadata(self, tmp_path: Path) -> None:
        """shutil.copy2 should preserve file metadata (e.g. modification time)."""
        src = tmp_path / "meta.txt"
        src.write_text("metadata test")

        # Read the source mtime (may have limited resolution on some OS)
        src_mtime = src.stat().st_mtime

        prefix = tmp_path / "archive"
        store = LocalStorage(path_prefix=str(prefix))

        result = await store.save_file(src, key="meta")
        dest_mtime = Path(result).stat().st_mtime

        # Allow small floating-point differences due to filesystem resolution
        assert abs(dest_mtime - src_mtime) < 1.0


# ---------------------------------------------------------------------------
# LocalStorage — error cases
# ---------------------------------------------------------------------------


class TestLocalStorageSaveFileErrors:
    """Test LocalStorage.save_file error handling."""

    async def test_file_not_found_raises(self, tmp_path: Path) -> None:
        """FileNotFoundError should be raised if the source file doesn't exist."""
        prefix = tmp_path / "archive"
        store = LocalStorage(path_prefix=str(prefix))

        with pytest.raises(FileNotFoundError, match="Local file not found"):
            await store.save_file(tmp_path / "nonexistent.txt", key="key")

    async def test_source_is_directory_raises(self, tmp_path: Path) -> None:
        """FileNotFoundError should be raised if the source path is a directory."""
        src_dir = tmp_path / "adir"
        src_dir.mkdir()

        prefix = tmp_path / "archive"
        store = LocalStorage(path_prefix=str(prefix))

        with pytest.raises(FileNotFoundError, match="Local file not found"):
            await store.save_file(src_dir, key="key")

    async def test_readonly_source_destination_unwritable(self, tmp_path: Path) -> None:
        """StorageError should be raised if the destination directory is not writable."""
        src = tmp_path / "file.txt"
        src.write_text("content")

        prefix = tmp_path / "archive"
        prefix.mkdir()

        # Make the prefix directory read-only
        os.chmod(prefix, 0o444)

        store = LocalStorage(path_prefix=str(prefix))

        try:
            with pytest.raises(StorageError, match="Failed to save"):
                await store.save_file(src, key="subdir")
        finally:
            # Restore permissions so tmp_path cleanup can succeed
            os.chmod(prefix, 0o755)


# ---------------------------------------------------------------------------
# GDrive inherits Storage / StorageError
# ---------------------------------------------------------------------------


class TestGDriveStorageIntegration:
    """Verify GDrive integrates with the Storage interface properly."""

    def test_gdrive_error_is_storage_error(self) -> None:
        """GDriveError should be a subclass of StorageError."""
        from app.gdrive import GDriveError

        assert issubclass(GDriveError, StorageError)

    def test_gdrive_is_storage(self) -> None:
        """GDrive should be a subclass of Storage."""
        from app.gdrive import GDrive

        assert issubclass(GDrive, Storage)

    def test_upload_error_is_storage_error(self) -> None:
        """UploadError (a GDriveError subclass) should also be a StorageError."""
        from app.gdrive import GDriveError, UploadError

        assert issubclass(UploadError, StorageError)
        assert issubclass(UploadError, GDriveError)
