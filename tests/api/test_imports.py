"""Tests for the notes-import API endpoints."""

from __future__ import annotations

import io
import uuid
import zipfile
from collections.abc import Generator, Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

import assistant.api.routes.imports as imports_routes
from assistant.adapters.notes_import import ImportReport
from assistant.api.app import create_app
from assistant.api.dependencies import ImportSettings, get_session
from assistant.models.schema import Note, User
from assistant.notes.service import add_markdown_node

# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def import_root(tmp_path: Path) -> Path:
    return tmp_path / "imports"


@pytest.fixture
def client(db_session: Session, import_root: Path) -> Iterator[TestClient]:
    def override_get_session() -> Generator[Session]:
        try:
            yield db_session
        except Exception:
            db_session.rollback()
            raise

    app = create_app(
        import_settings=ImportSettings(storage_root=import_root, max_upload_bytes=50_000),
    )
    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app, raise_server_exceptions=True) as tc:
        yield tc


def _zip_bytes(entries: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _note_html(title: str, body: str = "content") -> str:
    return f"<html><body><h1>{title}</h1><p>{body}</p></body></html>"


def _upload(
    client: TestClient,
    headers: dict[str, str],
    data: bytes,
) -> uuid.UUID:
    resp = client.post(
        "/imports",
        files={"file": ("export.zip", data, "application/zip")},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["import_id"])


def _files_under(root: Path) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


# ── POST /imports ─────────────────────────────────────────────────────────────


def test_upload_stores_zip_under_user_dir(
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    import_root: Path,
) -> None:
    import_id = _upload(client, auth_headers, _zip_bytes({"NB/a.html": _note_html("A")}))

    assert _files_under(import_root) == [
        import_root / str(test_user.uid) / f"{import_id}.zip",
    ]


def test_upload_non_zip_returns_400(
    client: TestClient, auth_headers: dict[str, str], import_root: Path
) -> None:
    resp = client.post(
        "/imports",
        files={"file": ("export.zip", b"not a zip", "application/zip")},
        headers=auth_headers,
    )

    assert resp.status_code == 400
    assert _files_under(import_root) == []


def test_upload_too_large_returns_413(
    client: TestClient, auth_headers: dict[str, str], import_root: Path
) -> None:
    big = _zip_bytes({"NB/a.html": "".join(str(uuid.uuid4()) for _ in range(5_000))})
    assert len(big) > 50_000

    resp = client.post(
        "/imports",
        files={"file": ("export.zip", big, "application/zip")},
        headers=auth_headers,
    )

    assert resp.status_code == 413
    assert _files_under(import_root) == []


def test_upload_requires_authentication(client: TestClient) -> None:
    resp = client.post(
        "/imports",
        files={"file": ("export.zip", _zip_bytes({"NB/a.html": "x"}), "application/zip")},
    )

    assert resp.status_code == 401


# ── POST /imports/{import_id}/run ─────────────────────────────────────────────


def test_upload_then_run_imports_and_returns_report(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    import_root: Path,
) -> None:
    import_id = _upload(
        client,
        auth_headers,
        _zip_bytes(
            {
                "Work/a.html": _note_html("A"),
                "Work/b.html": _note_html("B"),
                "Personal/c.html": _note_html("C"),
            },
        ),
    )

    resp = client.post(
        f"/imports/{import_id}/run",
        json={"include_web_clips": False},
        headers=auth_headers,
    )

    assert resp.status_code == 200, resp.text
    report = resp.json()
    assert report["created"] == 3
    assert report["notebooks_touched"] == 2
    assert report["kept_modified"] == []
    assert {n.title for n in db_session.scalars(select(Note))} == {"A", "B", "C"}
    assert _files_under(import_root) == []


def test_rerun_reports_edited_note_with_ids_for_linking(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    test_user: User,
) -> None:
    data = _zip_bytes({"Work/a.html": _note_html("A"), "Work/b.html": _note_html("B")})
    first = _upload(client, auth_headers, data)
    client.post(f"/imports/{first}/run", json={}, headers=auth_headers)
    edited = db_session.scalar(select(Note).where(Note.title == "A"))
    assert edited is not None
    add_markdown_node(db_session, edited.id, test_user, "my edit", "paragraph")
    db_session.commit()

    second = _upload(client, auth_headers, data)
    resp = client.post(f"/imports/{second}/run", json={}, headers=auth_headers)

    report = resp.json()
    assert report["unchanged"] == 1
    assert len(report["kept_modified"]) == 1
    kept = report["kept_modified"][0]
    assert kept["note_id"] == str(edited.id)
    assert kept["notebook_id"] == str(edited.notebook_id)
    assert kept["title"] == "A"
    assert kept["notebook"] == "Work"
    assert kept["source_path"] == "Work/a.html"
    assert kept["imported_at"] is not None
    assert kept["modified_at"] is not None


def test_run_forwards_include_web_clips(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    import_id = _upload(client, auth_headers, _zip_bytes({"NB/a.html": _note_html("A")}))

    with patch.object(
        imports_routes, "import_zip", return_value=ImportReport()
    ) as mock_import:
        resp = client.post(
            f"/imports/{import_id}/run",
            json={"include_web_clips": True},
            headers=auth_headers,
        )

    assert resp.status_code == 200
    assert mock_import.call_args.kwargs["include_web_clips"] is True


def test_run_unknown_import_returns_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.post(f"/imports/{uuid.uuid4()}/run", json={}, headers=auth_headers)

    assert resp.status_code == 404


def test_run_another_users_import_returns_404(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
    import_root: Path,
) -> None:
    import_id = _upload(client, auth_headers, _zip_bytes({"NB/a.html": _note_html("A")}))

    resp = client.post(f"/imports/{import_id}/run", json={}, headers=other_auth_headers)

    assert resp.status_code == 404
    assert len(_files_under(import_root)) == 1


def test_run_unsafe_zip_returns_400_and_deletes_it(
    client: TestClient, auth_headers: dict[str, str], import_root: Path
) -> None:
    import_id = _upload(client, auth_headers, _zip_bytes({"../evil.html": "x"}))

    resp = client.post(f"/imports/{import_id}/run", json={}, headers=auth_headers)

    assert resp.status_code == 400
    assert "Unsafe path" in resp.json()["detail"]
    assert _files_under(import_root) == []


def test_run_requires_authentication(client: TestClient) -> None:
    resp = client.post(f"/imports/{uuid.uuid4()}/run", json={})

    assert resp.status_code == 401
