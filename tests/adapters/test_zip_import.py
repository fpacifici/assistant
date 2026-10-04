"""Tests for storing, extracting and importing an uploaded notes zip."""

from __future__ import annotations

import io
import stat
import uuid
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

import assistant.adapters.zip_import as zip_import_module
from assistant.adapters.zip_import import (
    ImportNotFoundError,
    InvalidImportArchiveError,
    UploadTooLargeError,
    import_zip,
    store_upload,
)
from assistant.models.schema import Note, Notebook, User


def _make_user(session: Session, email: str = "importer@test.com") -> User:
    user = User(email=email, firstname="A", lastname="B")
    session.add(user)
    session.flush()
    return user


def _note_html(title: str, body: str = "content") -> str:
    return f"<html><body><h1>{title}</h1><p>{body}</p></body></html>"


def _zip_bytes(entries: dict[str, str | bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _store(
    storage: Path,
    user: User,
    entries: dict[str, str | bytes] | bytes,
) -> uuid.UUID:
    data = entries if isinstance(entries, bytes) else _zip_bytes(entries)
    return store_upload(
        io.BytesIO(data),
        user,
        storage_root=storage,
        max_bytes=10 * 1024 * 1024,
    )


def _user_dir(storage: Path, user: User) -> Path:
    return storage / str(user.uid)


def _titles_by_notebook(session: Session) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for note in session.scalars(select(Note)):
        result.setdefault(note.notebook.name, set()).add(note.title)
    return result


# ---------------------------------------------------------------------------
# store_upload
# ---------------------------------------------------------------------------


def test_store_upload_writes_zip_under_user_dir(
    tmp_path: Path, db_session: Session
) -> None:
    user = _make_user(db_session)

    import_id = _store(tmp_path, user, {"NB/a.html": _note_html("A")})

    assert [p.name for p in _user_dir(tmp_path, user).iterdir()] == [f"{import_id}.zip"]


def test_store_upload_rejects_non_zip_and_cleans_up(
    tmp_path: Path, db_session: Session
) -> None:
    user = _make_user(db_session)

    with pytest.raises(InvalidImportArchiveError):
        _store(tmp_path, user, b"definitely not a zip")

    assert list(_user_dir(tmp_path, user).iterdir()) == []


def test_store_upload_rejects_too_large_and_cleans_up(
    tmp_path: Path, db_session: Session
) -> None:
    user = _make_user(db_session)
    data = _zip_bytes({"NB/a.html": "x" * 10_000})

    with pytest.raises(UploadTooLargeError):
        store_upload(io.BytesIO(data), user, storage_root=tmp_path, max_bytes=100)

    assert list(_user_dir(tmp_path, user).iterdir()) == []


# ---------------------------------------------------------------------------
# import_zip — layouts
# ---------------------------------------------------------------------------


def test_import_zip_imports_one_notebook_per_directory(
    tmp_path: Path, db_session: Session
) -> None:
    user = _make_user(db_session)
    import_id = _store(
        tmp_path,
        user,
        {
            "Work/a.html": _note_html("A"),
            "Work/b.html": _note_html("B"),
            "Personal/c.html": _note_html("C"),
        },
    )

    report = import_zip(db_session, import_id, user, storage_root=tmp_path)

    assert report.created == 3
    assert _titles_by_notebook(db_session) == {"Work": {"A", "B"}, "Personal": {"C"}}


def test_import_zip_unwraps_a_single_wrapper_folder(
    tmp_path: Path, db_session: Session
) -> None:
    user = _make_user(db_session)
    import_id = _store(
        tmp_path,
        user,
        {
            "Export/Work/a.html": _note_html("A"),
            "Export/Personal/b.html": _note_html("B"),
        },
    )

    import_zip(db_session, import_id, user, storage_root=tmp_path)

    assert _titles_by_notebook(db_session) == {"Work": {"A"}, "Personal": {"B"}}


def test_import_zip_single_notebook_folder_is_not_unwrapped(
    tmp_path: Path, db_session: Session
) -> None:
    user = _make_user(db_session)
    import_id = _store(tmp_path, user, {"Work/a.html": _note_html("A")})

    import_zip(db_session, import_id, user, storage_root=tmp_path)

    assert _titles_by_notebook(db_session) == {"Work": {"A"}}


def test_import_zip_ignores_macos_metadata(tmp_path: Path, db_session: Session) -> None:
    user = _make_user(db_session)
    import_id = _store(
        tmp_path,
        user,
        {
            "Work/a.html": _note_html("A"),
            "Work/.DS_Store": b"\x00",
            "__MACOSX/Work/._a.html": b"\x00\x05\x16\x07",
        },
    )

    report = import_zip(db_session, import_id, user, storage_root=tmp_path)

    assert report.created == 1
    assert report.failed == []
    assert {nb.name for nb in db_session.scalars(select(Notebook))} == {"Work"}


def test_import_zip_handles_non_ascii_notebook_names(
    tmp_path: Path, db_session: Session
) -> None:
    user = _make_user(db_session)
    import_id = _store(tmp_path, user, {"Ricette è più/pasta.html": _note_html("Pasta")})

    import_zip(db_session, import_id, user, storage_root=tmp_path)

    assert _titles_by_notebook(db_session) == {"Ricette è più": {"Pasta"}}


def test_import_zip_passes_include_web_clips(tmp_path: Path, db_session: Session) -> None:
    user = _make_user(db_session)
    import_id = _store(tmp_path, user, {"NB/a.html": _note_html("A")})

    with patch.object(zip_import_module, "run_import") as mock_run:
        import_zip(
            db_session,
            import_id,
            user,
            storage_root=tmp_path,
            include_web_clips=True,
        )

    source = mock_run.call_args.args[1]
    assert source.include_web_clips is True


def test_import_zip_without_notebook_folders_is_rejected(
    tmp_path: Path, db_session: Session
) -> None:
    user = _make_user(db_session)
    import_id = _store(tmp_path, user, {"loose.html": _note_html("Loose")})

    with pytest.raises(InvalidImportArchiveError, match="No notes found"):
        import_zip(db_session, import_id, user, storage_root=tmp_path)


def test_importing_the_same_zip_twice_changes_nothing(
    tmp_path: Path, db_session: Session
) -> None:
    user = _make_user(db_session)
    entries: dict[str, str | bytes] = {
        "Work/a.html": _note_html("A"),
        "Personal/b.html": _note_html("B"),
    }
    import_zip(db_session, _store(tmp_path, user, entries), user, storage_root=tmp_path)

    report = import_zip(
        db_session, _store(tmp_path, user, entries), user, storage_root=tmp_path
    )

    assert report.created == 0
    assert report.refreshed == 0
    assert report.unchanged == 2


# ---------------------------------------------------------------------------
# import_zip — unsafe archives
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["../evil.html", "NB/../../evil.html", "/abs/evil.html", "C:/evil.html"],
)
def test_import_zip_rejects_unsafe_paths(
    tmp_path: Path, db_session: Session, name: str
) -> None:
    user = _make_user(db_session)
    storage = tmp_path / "storage"
    import_id = _store(storage, user, {"NB/a.html": _note_html("A"), name: "x"})

    with pytest.raises(InvalidImportArchiveError, match="Unsafe path"):
        import_zip(db_session, import_id, user, storage_root=storage)

    assert not (tmp_path / "evil.html").exists()
    assert list(db_session.scalars(select(Note))) == []


def test_import_zip_rejects_symlinks(tmp_path: Path, db_session: Session) -> None:
    user = _make_user(db_session)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("NB/a.html", _note_html("A"))
        link = zipfile.ZipInfo("NB/link.html")
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, "/etc/passwd")
    import_id = _store(tmp_path, user, buffer.getvalue())

    with pytest.raises(InvalidImportArchiveError, match="Symbolic link"):
        import_zip(db_session, import_id, user, storage_root=tmp_path)


def test_import_zip_enforces_entry_count_limit(
    tmp_path: Path, db_session: Session
) -> None:
    user = _make_user(db_session)
    entries: dict[str, str | bytes] = {
        f"NB/{i}.html": _note_html(str(i)) for i in range(5)
    }
    import_id = _store(tmp_path, user, entries)

    with pytest.raises(InvalidImportArchiveError, match="entries"):
        import_zip(db_session, import_id, user, storage_root=tmp_path, max_entries=4)


def test_import_zip_enforces_uncompressed_size_limit(
    tmp_path: Path, db_session: Session
) -> None:
    user = _make_user(db_session)
    import_id = _store(tmp_path, user, {"NB/a.html": "x" * 10_000})

    with pytest.raises(InvalidImportArchiveError, match="expands"):
        import_zip(
            db_session,
            import_id,
            user,
            storage_root=tmp_path,
            max_uncompressed_bytes=1_000,
        )


# ---------------------------------------------------------------------------
# import_zip — ownership and cleanup
# ---------------------------------------------------------------------------


def test_import_zip_unknown_id_raises_not_found(
    tmp_path: Path, db_session: Session
) -> None:
    user = _make_user(db_session)

    with pytest.raises(ImportNotFoundError):
        import_zip(db_session, uuid.uuid4(), user, storage_root=tmp_path)


def test_import_zip_cannot_run_another_users_upload(
    tmp_path: Path, db_session: Session
) -> None:
    owner = _make_user(db_session)
    other = _make_user(db_session, "other@test.com")
    import_id = _store(tmp_path, owner, {"NB/a.html": _note_html("A")})

    with pytest.raises(ImportNotFoundError):
        import_zip(db_session, import_id, other, storage_root=tmp_path)

    assert (_user_dir(tmp_path, owner) / f"{import_id}.zip").exists()


def test_import_zip_deletes_zip_and_extracted_files_on_success(
    tmp_path: Path, db_session: Session
) -> None:
    user = _make_user(db_session)
    import_id = _store(tmp_path, user, {"NB/a.html": _note_html("A")})

    import_zip(db_session, import_id, user, storage_root=tmp_path)

    assert list(_user_dir(tmp_path, user).iterdir()) == []


def test_import_zip_deletes_files_when_import_raises(
    tmp_path: Path, db_session: Session
) -> None:
    user = _make_user(db_session)
    import_id = _store(tmp_path, user, {"NB/a.html": _note_html("A")})

    with (
        patch.object(zip_import_module, "run_import", side_effect=RuntimeError("db")),
        pytest.raises(RuntimeError),
    ):
        import_zip(db_session, import_id, user, storage_root=tmp_path)

    assert list(_user_dir(tmp_path, user).iterdir()) == []


def test_import_zip_deletes_files_when_archive_is_unsafe(
    tmp_path: Path, db_session: Session
) -> None:
    user = _make_user(db_session)
    import_id = _store(tmp_path, user, {"../evil.html": "x"})

    with pytest.raises(InvalidImportArchiveError):
        import_zip(db_session, import_id, user, storage_root=tmp_path)

    assert list(_user_dir(tmp_path, user).iterdir()) == []


def test_import_zip_corrupt_archive_is_rejected(
    tmp_path: Path, db_session: Session
) -> None:
    user = _make_user(db_session)
    data = bytearray(_zip_bytes({"NB/a.html": _note_html("A") * 50}))
    import_id = _store(tmp_path, user, bytes(data))
    zip_path = _user_dir(tmp_path, user) / f"{import_id}.zip"
    # Corrupt the compressed data of the first entry (after its local header).
    corrupted = bytearray(zip_path.read_bytes())
    for i in range(40, 60):
        corrupted[i] ^= 0xFF
    zip_path.write_bytes(bytes(corrupted))

    with pytest.raises(InvalidImportArchiveError):
        import_zip(db_session, import_id, user, storage_root=tmp_path)

    assert list(_user_dir(tmp_path, user).iterdir()) == []
