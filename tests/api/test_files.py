"""Tests for File API endpoints."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from assistant.api.app import create_app
from assistant.api.dependencies import get_session, get_storage
from assistant.attachments.service import (
    FILE_UPLOAD_TTL_HOURS,
    complete_file,
    create_file,
    upload_chunk,
)
from assistant.attachments.storage import LocalFileStorage
from assistant.auth.service import create_access_token
from assistant.models.schema import File, FileState, Note, Notebook, User
from assistant.notes.service import create_note, create_notebook

# ── extra fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def file_storage(tmp_path: Path) -> LocalFileStorage:
    return LocalFileStorage(tmp_path / "files")


@pytest.fixture
def client(db_session: Session, file_storage: LocalFileStorage) -> Iterator[TestClient]:
    def override_get_session() -> Iterator[Session]:
        try:
            yield db_session
        except Exception:
            db_session.rollback()
            raise

    def override_get_storage() -> LocalFileStorage:
        return file_storage

    app = create_app(file_storage=file_storage)
    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_storage] = override_get_storage
    with TestClient(app, raise_server_exceptions=True) as tc:
        yield tc


@pytest.fixture
def notebook(db_session: Session, test_user: User) -> Notebook:
    return create_notebook(db_session, "NB", test_user.uid)


@pytest.fixture
def note(db_session: Session, test_user: User, notebook: Notebook) -> Note:
    return create_note(db_session, notebook.id, test_user.uid, "Note")


# ── POST /files ───────────────────────────────────────────────────────────────


def test_create_file_returns_201(
    client: TestClient, auth_headers: dict[str, str], note: Note
) -> None:
    resp = client.post(
        "/files",
        json={"note_id": str(note.id), "file_name": "photo.png"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["file_name"] == "photo.png"
    assert data["state"] == FileState.PENDING.value
    assert data["note_id"] == str(note.id)


def test_create_file_wrong_user_returns_404(
    client: TestClient, db_session: Session, note: Note
) -> None:
    other = User(email="stranger@x.com", firstname="S", lastname="T")
    db_session.add(other)
    db_session.flush()
    token = create_access_token(other.uid)
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post(
        "/files",
        json={"note_id": str(note.id), "file_name": "x.bin"},
        headers=headers,
    )
    assert resp.status_code == 404


def test_create_file_unknown_note_returns_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.post(
        "/files",
        json={"note_id": str(uuid.uuid4()), "file_name": "x.bin"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


# ── PUT /files/{id}/parts/{n} ─────────────────────────────────────────────────


def test_upload_chunk_returns_204(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    note: Note,
    test_user: User,
) -> None:
    file = create_file(db_session, note.id, "f.bin", test_user.uid)
    resp = client.put(
        f"/files/{file.id}/parts/1",
        content=b"hello bytes",
        headers={**auth_headers, "Content-Type": "application/octet-stream"},
    )
    assert resp.status_code == 204


def test_upload_chunk_unknown_file_returns_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.put(
        f"/files/{uuid.uuid4()}/parts/1",
        content=b"data",
        headers={**auth_headers, "Content-Type": "application/octet-stream"},
    )
    assert resp.status_code == 404


def test_upload_chunk_expired_returns_410(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    note: Note,
    test_user: User,
) -> None:
    file = create_file(db_session, note.id, "f.bin", test_user.uid)
    file.creation_timestamp = datetime.now(UTC) - timedelta(
        hours=FILE_UPLOAD_TTL_HOURS + 1
    )
    db_session.flush()
    resp = client.put(
        f"/files/{file.id}/parts/1",
        content=b"data",
        headers={**auth_headers, "Content-Type": "application/octet-stream"},
    )
    assert resp.status_code == 410


# ── PATCH /files/{id} ────────────────────────────────────────────────────────


def test_complete_file_returns_200(  # noqa: PLR0913
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    file_storage: LocalFileStorage,
    note: Note,
    test_user: User,
) -> None:
    file = create_file(db_session, note.id, "f.bin", test_user.uid)
    upload_chunk(db_session, file_storage, file.id, 1, b"data", test_user.uid)
    resp = client.patch(f"/files/{file.id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["state"] == FileState.COMPLETE.value


def test_complete_file_not_uploading_returns_409(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    note: Note,
    test_user: User,
) -> None:
    file = create_file(db_session, note.id, "f.bin", test_user.uid)
    resp = client.patch(f"/files/{file.id}", headers=auth_headers)
    assert resp.status_code == 409


# ── GET /files/{id} ───────────────────────────────────────────────────────────


def test_download_file_returns_bytes(  # noqa: PLR0913
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    file_storage: LocalFileStorage,
    note: Note,
    test_user: User,
) -> None:
    file = create_file(db_session, note.id, "hello.txt", test_user.uid)
    upload_chunk(db_session, file_storage, file.id, 1, b"file content", test_user.uid)
    complete_file(db_session, file_storage, file.id, test_user.uid)
    resp = client.get(f"/files/{file.id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.content == b"file content"
    assert "attachment" in resp.headers["content-disposition"]


def test_download_file_not_complete_returns_409(  # noqa: PLR0913
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    file_storage: LocalFileStorage,
    note: Note,
    test_user: User,
) -> None:
    file = create_file(db_session, note.id, "f.bin", test_user.uid)
    upload_chunk(db_session, file_storage, file.id, 1, b"x", test_user.uid)
    resp = client.get(f"/files/{file.id}", headers=auth_headers)
    assert resp.status_code == 409


# ── DELETE /files/{id} ────────────────────────────────────────────────────────


def test_delete_file_returns_204(  # noqa: PLR0913
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    file_storage: LocalFileStorage,
    note: Note,
    test_user: User,
) -> None:
    file = create_file(db_session, note.id, "del.txt", test_user.uid)
    upload_chunk(db_session, file_storage, file.id, 1, b"bye", test_user.uid)
    complete_file(db_session, file_storage, file.id, test_user.uid)
    resp = client.delete(f"/files/{file.id}", headers=auth_headers)
    assert resp.status_code == 204
    assert db_session.get(File, file.id) is None


def test_delete_file_wrong_user_returns_404(
    client: TestClient,
    db_session: Session,
    file_storage: LocalFileStorage,  # noqa: ARG001
    note: Note,
    test_user: User,
) -> None:
    other = User(email="evil@example.com", firstname="E", lastname="V")
    db_session.add(other)
    db_session.flush()
    file = create_file(db_session, note.id, "f.bin", test_user.uid)
    token = create_access_token(other.uid)
    resp = client.delete(
        f"/files/{file.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
