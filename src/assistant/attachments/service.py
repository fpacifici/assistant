"""Attachment service — business logic for chunked file uploads."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from assistant.attachments.exceptions import (
    AttachmentNotFoundError,
    FileAccessDeniedError,
    FileExpiredError,
    FileStateError,
)
from assistant.models.schema import Chunk, File, FileState, Note

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session

    from assistant.attachments.storage import FileStorage

FILE_UPLOAD_TTL_HOURS = 24


def _get_file(session: Session, file_id: uuid.UUID) -> File:
    file = session.get(File, file_id)
    if file is None:
        raise AttachmentNotFoundError(file_id)
    return file


def _check_ttl(file: File) -> None:
    """Transition file to expired if its TTL has elapsed; raise FileExpiredError."""
    if file.state in (FileState.COMPLETE.value, FileState.EXPIRED.value):
        return
    cutoff = file.creation_timestamp + timedelta(hours=FILE_UPLOAD_TTL_HOURS)
    if datetime.now(UTC) > cutoff:
        file.state = FileState.EXPIRED.value
        raise FileExpiredError(file.id)


def _check_owner(session: Session, file: File, user_id: uuid.UUID) -> None:
    note = session.get(Note, file.note_id)
    if note is None or note.owner_id != user_id:
        raise FileAccessDeniedError(file.id)


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------


def create_file(
    session: Session,
    note_id: uuid.UUID,
    file_name: str,
    uploader_id: uuid.UUID,
) -> File:
    """Create a new file upload record in pending state.

    Raises:
        FileAccessDeniedError: If uploader_id is not the note owner.
    """
    note = session.get(Note, note_id)
    if note is None or note.owner_id != uploader_id:
        raise FileAccessDeniedError(note_id)

    file = File(
        note_id=note_id,
        file_name=file_name,
        state=FileState.PENDING.value,
    )
    session.add(file)
    session.flush()
    return file


def upload_chunk(  # noqa: PLR0913
    session: Session,
    storage: FileStorage,
    file_id: uuid.UUID,
    part_number: int,
    data: bytes,
    uploader_id: uuid.UUID,
) -> Chunk:
    """Upload one chunk of a file.

    Transitions the file from pending to uploading on the first chunk.

    Raises:
        FileNotFoundError: File record doesn't exist.
        FileAccessDeniedError: User is not the note owner.
        FileExpiredError: Upload TTL has elapsed.
        FileStateError: File is already complete.
    """
    file = _get_file(session, file_id)
    _check_owner(session, file, uploader_id)
    _check_ttl(file)

    if file.state == FileState.COMPLETE.value:
        raise FileStateError(file_id, file.state, "pending or uploading")

    disk_path = storage.write_chunk(file_id, part_number, data)

    chunk = Chunk(
        file_id=file_id,
        part_number=part_number,
        file_name=disk_path,
    )
    session.add(chunk)

    if file.state == FileState.PENDING.value:
        file.state = FileState.UPLOADING.value

    session.flush()
    return chunk


def complete_file(
    session: Session,
    storage: FileStorage,
    file_id: uuid.UUID,
    uploader_id: uuid.UUID,
) -> File:
    """Merge all chunks into a single file and mark the upload complete.

    Raises:
        FileNotFoundError: File record doesn't exist.
        FileAccessDeniedError: User is not the note owner.
        FileExpiredError: Upload TTL has elapsed.
        FileStateError: File is not in uploading state.
    """
    file = _get_file(session, file_id)
    _check_owner(session, file, uploader_id)
    _check_ttl(file)

    if file.state != FileState.UPLOADING.value:
        raise FileStateError(file_id, file.state, FileState.UPLOADING.value)

    # Merge chunks in part_number order (relationship is already ordered).
    chunk_paths = [c.file_name for c in file.chunks]
    storage.merge_chunks(file_id, chunk_paths)

    # Clean up chunk files from disk.
    for chunk in file.chunks:
        storage.delete_chunk(chunk.file_name)
        session.delete(chunk)

    file.state = FileState.COMPLETE.value
    session.flush()
    return file


def get_file_bytes(
    session: Session,
    storage: FileStorage,
    file_id: uuid.UUID,
    user_id: uuid.UUID,
) -> tuple[File, bytes]:
    """Return the File record and its raw bytes.

    Raises:
        FileNotFoundError: File record doesn't exist.
        FileAccessDeniedError: User is not the note owner.
        FileStateError: File is not complete.
    """
    file = _get_file(session, file_id)
    _check_owner(session, file, user_id)

    if file.state != FileState.COMPLETE.value:
        raise FileStateError(file_id, file.state, FileState.COMPLETE.value)

    data = storage.read_file(file_id)
    return file, data


def delete_file_record(
    session: Session,
    storage: FileStorage,
    file_id: uuid.UUID,
) -> None:
    """Delete a file record and all associated disk data.

    Idempotent — safe to call even if the file has already been removed.
    """
    file = session.get(File, file_id)
    if file is None:
        return

    # Remove chunk files from disk (DB cascade handles Chunk rows).
    for chunk in file.chunks:
        storage.delete_chunk(chunk.file_name)

    # Remove the merged file directory if present.
    if file.state == FileState.COMPLETE.value:
        storage.delete_file(file_id)

    session.delete(file)
    session.flush()
