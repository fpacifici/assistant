"""Unit tests for LocalFileStorage."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from assistant.attachments.storage import LocalFileStorage


@pytest.fixture
def storage(tmp_path: Path) -> LocalFileStorage:
    return LocalFileStorage(tmp_path / "files")


def test_write_and_read_chunk(storage: LocalFileStorage) -> None:
    file_id = uuid.uuid4()
    data = b"hello chunk"
    path = storage.write_chunk(file_id, 1, data)
    assert Path(path).exists()
    assert storage.read_chunk(path) == data


def test_write_chunk_creates_directory(storage: LocalFileStorage) -> None:
    file_id = uuid.uuid4()
    storage.write_chunk(file_id, 1, b"x")
    assert (storage.base_path / str(file_id)).is_dir()


def test_merge_chunks(storage: LocalFileStorage) -> None:
    file_id = uuid.uuid4()
    path1 = storage.write_chunk(file_id, 1, b"foo")
    path2 = storage.write_chunk(file_id, 2, b"bar")
    storage.merge_chunks(file_id, [path1, path2])
    assert storage.read_file(file_id) == b"foobar"


def test_delete_chunk(storage: LocalFileStorage) -> None:
    file_id = uuid.uuid4()
    path = storage.write_chunk(file_id, 1, b"data")
    storage.delete_chunk(path)
    assert not Path(path).exists()


def test_delete_chunk_is_idempotent(storage: LocalFileStorage) -> None:
    storage.delete_chunk("/nonexistent/path/chunk_1")


def test_delete_file_removes_directory(storage: LocalFileStorage) -> None:
    file_id = uuid.uuid4()
    path = storage.write_chunk(file_id, 1, b"data")
    storage.merge_chunks(file_id, [path])
    storage.delete_file(file_id)
    assert not (storage.base_path / str(file_id)).exists()


def test_delete_file_is_idempotent(storage: LocalFileStorage) -> None:
    storage.delete_file(uuid.uuid4())


def test_merge_chunks_preserves_order(storage: LocalFileStorage) -> None:
    file_id = uuid.uuid4()
    path1 = storage.write_chunk(file_id, 1, b"A")
    path2 = storage.write_chunk(file_id, 2, b"B")
    path3 = storage.write_chunk(file_id, 3, b"C")
    # Deliberately pass them in sorted order as the service will.
    storage.merge_chunks(file_id, [path1, path2, path3])
    assert storage.read_file(file_id) == b"ABC"
