"""File storage abstraction and local filesystem implementation."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    import uuid


@runtime_checkable
class FileStorage(Protocol):
    """Protocol for pluggable file storage backends."""

    def write_chunk(self, file_id: uuid.UUID, part_number: int, data: bytes) -> str:
        """Write one chunk to storage and return its storage path."""
        ...

    def read_chunk(self, path: str) -> bytes:
        """Read a chunk from storage by its path."""
        ...

    def merge_chunks(self, file_id: uuid.UUID, chunk_paths: list[str]) -> None:
        """Merge ordered chunks into a single complete file on storage."""
        ...

    def read_file(self, file_id: uuid.UUID) -> bytes:
        """Read the complete merged file."""
        ...

    def delete_chunk(self, path: str) -> None:
        """Delete a chunk from storage. No-op if path does not exist."""
        ...

    def delete_file(self, file_id: uuid.UUID) -> None:
        """Delete the complete file (and its directory) from storage. No-op if absent."""
        ...


class LocalFileStorage:
    """Stores files on the local filesystem.

    Layout::

        {base_path}/{file_id}/chunk_{part_number}   ← individual chunks
        {base_path}/{file_id}/file                  ← merged complete file
    """

    def __init__(self, base_path: Path) -> None:
        self.base_path = base_path
        base_path.mkdir(parents=True, exist_ok=True)

    def _file_dir(self, file_id: uuid.UUID) -> Path:
        return self.base_path / str(file_id)

    def write_chunk(self, file_id: uuid.UUID, part_number: int, data: bytes) -> str:
        file_dir = self._file_dir(file_id)
        file_dir.mkdir(parents=True, exist_ok=True)
        chunk_path = file_dir / f"chunk_{part_number}"
        chunk_path.write_bytes(data)
        return str(chunk_path)

    def read_chunk(self, path: str) -> bytes:
        return Path(path).read_bytes()

    def merge_chunks(self, file_id: uuid.UUID, chunk_paths: list[str]) -> None:
        file_dir = self._file_dir(file_id)
        file_dir.mkdir(parents=True, exist_ok=True)
        dest = file_dir / "file"
        with dest.open("wb") as out:
            for path in chunk_paths:
                out.write(Path(path).read_bytes())

    def read_file(self, file_id: uuid.UUID) -> bytes:
        return (self._file_dir(file_id) / "file").read_bytes()

    def delete_chunk(self, path: str) -> None:
        p = Path(path)
        if p.exists():
            p.unlink()

    def delete_file(self, file_id: uuid.UUID) -> None:
        file_dir = self._file_dir(file_id)
        if file_dir.exists():
            shutil.rmtree(file_dir)
