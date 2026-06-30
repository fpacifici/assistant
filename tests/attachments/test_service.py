"""Unit tests for the attachments service."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from assistant.attachments.exceptions import (
    AttachmentNotFoundError,
    FileAccessDeniedError,
    FileExpiredError,
    FileStateError,
)
from assistant.attachments.service import (
    FILE_UPLOAD_TTL_HOURS,
    complete_file,
    create_file,
    delete_file_record,
    get_file_bytes,
    upload_chunk,
)
from assistant.attachments.storage import LocalFileStorage
from assistant.models.schema import File, FileState, Note, Notebook, User

# ── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def storage(tmp_path: Path) -> LocalFileStorage:
    return LocalFileStorage(tmp_path / "files")


@pytest.fixture
def user(db_session: Session) -> User:
    u = User(email="a@example.com", firstname="A", lastname="B")
    db_session.add(u)
    db_session.flush()
    return u


@pytest.fixture
def notebook(db_session: Session, user: User) -> Notebook:
    nb = Notebook(name="nb", owner_id=user.uid)
    db_session.add(nb)
    db_session.flush()
    return nb


@pytest.fixture
def note(db_session: Session, user: User, notebook: Notebook) -> Note:
    n = Note(
        notebook_id=notebook.id,
        owner_id=user.uid,
        title="Test Note",
        update_timestamp=datetime.now(UTC),
    )
    db_session.add(n)
    db_session.flush()
    return n


# ── create_file ─────────────────────────────────────────────────────────────


def test_create_file_returns_pending(db_session: Session, user: User, note: Note) -> None:
    file = create_file(db_session, note.id, "photo.png", user.uid)
    assert file.state == FileState.PENDING.value
    assert file.file_name == "photo.png"
    assert file.note_id == note.id


def test_create_file_wrong_user_raises(db_session: Session, note: Note) -> None:
    other_user = User(email="other@example.com", firstname="O", lastname="T")
    db_session.add(other_user)
    db_session.flush()
    with pytest.raises(FileAccessDeniedError):
        create_file(db_session, note.id, "file.txt", other_user.uid)


def test_create_file_unknown_note_raises(db_session: Session, user: User) -> None:
    with pytest.raises(FileAccessDeniedError):
        create_file(db_session, uuid.uuid4(), "file.txt", user.uid)


# ── upload_chunk ─────────────────────────────────────────────────────────────


def test_upload_chunk_transitions_to_uploading(
    db_session: Session, user: User, note: Note, storage: LocalFileStorage
) -> None:
    file = create_file(db_session, note.id, "doc.pdf", user.uid)
    upload_chunk(db_session, storage, file.id, 1, b"data", user.uid)
    db_session.refresh(file)
    assert file.state == FileState.UPLOADING.value


def test_upload_chunk_creates_chunk_record(
    db_session: Session, user: User, note: Note, storage: LocalFileStorage
) -> None:
    file = create_file(db_session, note.id, "doc.pdf", user.uid)
    chunk = upload_chunk(db_session, storage, file.id, 1, b"bytes", user.uid)
    assert chunk.part_number == 1
    assert chunk.file_id == file.id


def test_upload_chunk_unknown_file_raises(
    db_session: Session, user: User, storage: LocalFileStorage
) -> None:
    with pytest.raises(AttachmentNotFoundError):
        upload_chunk(db_session, storage, uuid.uuid4(), 1, b"x", user.uid)


def test_upload_chunk_wrong_user_raises(
    db_session: Session, user: User, note: Note, storage: LocalFileStorage
) -> None:
    other = User(email="x@example.com", firstname="X", lastname="Y")
    db_session.add(other)
    db_session.flush()
    file = create_file(db_session, note.id, "f.bin", user.uid)
    with pytest.raises(FileAccessDeniedError):
        upload_chunk(db_session, storage, file.id, 1, b"data", other.uid)


def test_upload_chunk_expired_file_raises(
    db_session: Session,
    user: User,
    note: Note,
    storage: LocalFileStorage,
) -> None:
    file = create_file(db_session, note.id, "f.bin", user.uid)
    old_time = datetime.now(UTC) - timedelta(hours=FILE_UPLOAD_TTL_HOURS + 1)
    file.creation_timestamp = old_time
    db_session.flush()
    with pytest.raises(FileExpiredError):
        upload_chunk(db_session, storage, file.id, 1, b"data", user.uid)


def test_upload_chunk_on_complete_file_raises(
    db_session: Session, user: User, note: Note, storage: LocalFileStorage
) -> None:
    file = create_file(db_session, note.id, "f.bin", user.uid)
    upload_chunk(db_session, storage, file.id, 1, b"data", user.uid)
    complete_file(db_session, storage, file.id, user.uid)
    with pytest.raises(FileStateError):
        upload_chunk(db_session, storage, file.id, 2, b"more", user.uid)


# ── complete_file ─────────────────────────────────────────────────────────────


def test_complete_file_merges_and_marks_complete(
    db_session: Session, user: User, note: Note, storage: LocalFileStorage
) -> None:
    file = create_file(db_session, note.id, "f.bin", user.uid)
    upload_chunk(db_session, storage, file.id, 1, b"hello ", user.uid)
    upload_chunk(db_session, storage, file.id, 2, b"world", user.uid)
    result = complete_file(db_session, storage, file.id, user.uid)
    assert result.state == FileState.COMPLETE.value
    assert storage.read_file(file.id) == b"hello world"


def test_complete_file_removes_chunk_records(
    db_session: Session, user: User, note: Note, storage: LocalFileStorage
) -> None:
    file = create_file(db_session, note.id, "f.bin", user.uid)
    upload_chunk(db_session, storage, file.id, 1, b"data", user.uid)
    complete_file(db_session, storage, file.id, user.uid)
    db_session.expire(file)
    assert len(file.chunks) == 0


def test_complete_file_not_uploading_raises(
    db_session: Session, user: User, note: Note, storage: LocalFileStorage
) -> None:
    file = create_file(db_session, note.id, "f.bin", user.uid)
    with pytest.raises(FileStateError):
        complete_file(db_session, storage, file.id, user.uid)


# ── get_file_bytes ─────────────────────────────────────────────────────────────


def test_get_file_bytes_returns_content(
    db_session: Session, user: User, note: Note, storage: LocalFileStorage
) -> None:
    file = create_file(db_session, note.id, "img.png", user.uid)
    upload_chunk(db_session, storage, file.id, 1, b"pixels", user.uid)
    complete_file(db_session, storage, file.id, user.uid)
    f, data = get_file_bytes(db_session, storage, file.id, user.uid)
    assert data == b"pixels"
    assert f.id == file.id


def test_get_file_bytes_not_complete_raises(
    db_session: Session, user: User, note: Note, storage: LocalFileStorage
) -> None:
    file = create_file(db_session, note.id, "img.png", user.uid)
    upload_chunk(db_session, storage, file.id, 1, b"data", user.uid)
    with pytest.raises(FileStateError):
        get_file_bytes(db_session, storage, file.id, user.uid)


# ── delete_file_record ─────────────────────────────────────────────────────────


def test_delete_file_record_removes_db_and_disk(
    db_session: Session, user: User, note: Note, storage: LocalFileStorage
) -> None:
    file = create_file(db_session, note.id, "del.txt", user.uid)
    upload_chunk(db_session, storage, file.id, 1, b"x", user.uid)
    complete_file(db_session, storage, file.id, user.uid)
    file_id = file.id
    delete_file_record(db_session, storage, file_id)
    assert db_session.get(File, file_id) is None
    assert not (storage.base_path / str(file_id)).exists()


def test_delete_file_record_idempotent(
    db_session: Session, storage: LocalFileStorage
) -> None:
    delete_file_record(db_session, storage, uuid.uuid4())
