"""Tests for the notes-import pipeline (`run_import`).

Real `db_session` fixture (SQLite) + a real fixture directory driven through
the real `HTMLFileImportSource`, plus a small in-memory fake `ImportSource`
for cases that need to isolate pipeline logic (dedup/refresh/error
resilience) from the filesystem.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.orm import Session

import assistant.adapters.notes_import as notes_import_module
from assistant.adapters.html_parser import ParsedBlock, ParsedNote
from assistant.adapters.import_source import ImportedNote, ImportSource
from assistant.adapters.notes_import import compute_external_id, run_import
from assistant.adapters.plugins.html_file import HTMLFileImportSource
from assistant.models.schema import Node, Note, Notebook, NoteImport, User
from assistant.notes.service import (
    add_markdown_node,
    create_note,
    create_notebook,
    get_note_by_external_id,
    get_note_import,
    get_note_update_timestamp,
    get_ordered_nodes,
    update_markdown_node,
    update_note,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "html_import"


def _make_user(session: Session, email: str = "importer@test.com") -> User:
    user = User(email=email, firstname="A", lastname="B")
    session.add(user)
    session.flush()
    return user


def _doc(notebook: str, title: str, *payloads: str) -> ImportedNote:
    return ImportedNote(
        notebook_name=notebook,
        parsed=ParsedNote(
            title=title,
            blocks=[ParsedBlock("paragraph", p) for p in payloads],
        ),
    )


def _note(session: Session, notebook: str, title: str) -> Note:
    nb = session.scalar(select(Notebook).where(Notebook.name == notebook))
    assert nb is not None
    note = get_note_by_external_id(session, nb.id, compute_external_id(title))
    assert note is not None
    return note


def _payloads(session: Session, note: Note, user: User) -> list[str | None]:
    return [n.payload for n in get_ordered_nodes(session, note.id, user)]


def _snapshot(session: Session) -> set[tuple[str, str, tuple[tuple[str, str], ...]]]:
    """(notebook, title, ordered (block_type, payload)) for every note."""
    result = set()
    for note in session.scalars(select(Note)):
        nodes = session.scalars(
            select(Node).where(Node.note_id == note.id).order_by(Node.position),
        )
        result.add(
            (
                note.notebook.name,
                note.title,
                tuple((n.block_type or "", n.payload or "") for n in nodes),
            ),
        )
    return result


class _FakeImportSource(ImportSource):
    """In-memory ImportSource for isolating pipeline logic from the filesystem."""

    def __init__(self, documents: dict[str, ImportedNote]) -> None:
        self._documents = documents

    def list_documents(self) -> list[str]:
        return list(self._documents.keys())

    def get_note(self, document_id: str) -> ImportedNote:
        return self._documents[document_id]


class _RaisingImportSource(ImportSource):
    """ImportSource whose get_note raises for a chosen document id."""

    def __init__(self, documents: dict[str, ImportedNote], *, broken_id: str) -> None:
        self._documents = documents
        self._broken_id = broken_id

    def list_documents(self) -> list[str]:
        return list(self._documents.keys())

    def get_note(self, document_id: str) -> ImportedNote:
        if document_id == self._broken_id:
            msg = "boom"
            raise ValueError(msg)
        return self._documents[document_id]


# ---------------------------------------------------------------------------
# Full pipeline against the real fixture directory
# ---------------------------------------------------------------------------


def test_run_import_creates_notebooks_and_notes_from_fixtures(
    db_session: Session,
) -> None:
    user = _make_user(db_session)
    source = HTMLFileImportSource(FIXTURES_DIR)

    report = run_import(db_session, source, user)

    assert report.created == 3
    assert report.skipped_web_clip == 1
    assert report.imported_web_clip == 0
    assert report.unchanged == 0
    assert report.refreshed == 0
    assert report.notebooks_touched == 2
    assert report.failed == []

    notebooks = {nb.name for nb in db_session.scalars(select(Notebook))}
    assert notebooks == {"Work", "Personal"}

    notes = list(db_session.scalars(select(Note)))
    assert len(notes) == 3
    titles = {n.title for n in notes}
    assert titles == {"First Note", "Second Note"}  # "First Note" appears twice


def test_run_import_tracks_every_created_note(db_session: Session) -> None:
    user = _make_user(db_session)
    run_import(db_session, HTMLFileImportSource(FIXTURES_DIR), user)

    records = {r.source_path for r in db_session.scalars(select(NoteImport))}
    assert records == {
        "Personal/idea.html",
        "Work/first-note.html",
        "Work/second-note.html",
    }
    for note in db_session.scalars(select(Note)):
        record = get_note_import(db_session, note.id)
        assert record is not None
        assert record.imported_at == get_note_update_timestamp(db_session, note.id)


def test_run_import_preserves_block_order_and_types(db_session: Session) -> None:
    user = _make_user(db_session)
    source = HTMLFileImportSource(FIXTURES_DIR)
    run_import(db_session, source, user)

    note = _note(db_session, "Work", "First Note")
    nodes = get_ordered_nodes(db_session, note.id, user)
    assert [(n.block_type, n.payload) for n in nodes] == [
        ("paragraph", "This is the first paragraph."),
        ("heading", "## A subsection"),
        ("list_item", "- Item one"),
        ("list_item", "- Item two"),
    ]


def test_run_import_ignores_files_nested_too_deep(db_session: Session) -> None:
    user = _make_user(db_session)
    source = HTMLFileImportSource(FIXTURES_DIR)
    run_import(db_session, source, user)

    titles = {n.title for n in db_session.scalars(select(Note))}
    assert "Too deep" not in titles


def test_importing_fixtures_twice_is_idempotent(db_session: Session) -> None:
    user = _make_user(db_session)
    source = HTMLFileImportSource(FIXTURES_DIR)
    run_import(db_session, source, user)
    snapshot_after_first = _snapshot(db_session)
    timestamps_after_first = {
        n.id: get_note_update_timestamp(db_session, n.id)
        for n in db_session.scalars(select(Note))
    }

    report = run_import(db_session, source, user)

    assert report.created == 0
    assert report.refreshed == 0
    assert report.unchanged == 3
    assert report.kept_modified == []
    assert _snapshot(db_session) == snapshot_after_first
    for note_id, timestamp in timestamps_after_first.items():
        assert get_note_update_timestamp(db_session, note_id) == timestamp


# ---------------------------------------------------------------------------
# Re-import of tracked notes
# ---------------------------------------------------------------------------


def test_unmodified_note_with_new_content_is_refreshed(db_session: Session) -> None:
    user = _make_user(db_session)
    run_import(db_session, _FakeImportSource({"NB/t.html": _doc("NB", "T", "v1")}), user)
    note = _note(db_session, "NB", "T")
    note_id, notebook_id = note.id, note.notebook_id
    record = get_note_import(db_session, note_id)
    assert record is not None
    first_imported_at = record.imported_at

    report = run_import(
        db_session,
        _FakeImportSource({"NB/t.html": _doc("NB", "T", "v2", "more")}),
        user,
    )

    assert report.refreshed == 1
    assert report.created == 0
    reloaded = _note(db_session, "NB", "T")
    assert reloaded.id == note_id
    assert reloaded.notebook_id == notebook_id
    assert _payloads(db_session, reloaded, user) == ["v2", "more"]
    record = get_note_import(db_session, note_id)
    assert record is not None
    assert record.imported_at > first_imported_at
    assert record.imported_at == get_note_update_timestamp(db_session, note_id)


def test_unmodified_note_with_identical_content_is_not_written(
    db_session: Session,
) -> None:
    user = _make_user(db_session)
    source = _FakeImportSource({"NB/t.html": _doc("NB", "T", "v1")})
    run_import(db_session, source, user)
    note = _note(db_session, "NB", "T")
    timestamp = get_note_update_timestamp(db_session, note.id)
    record = get_note_import(db_session, note.id)
    assert record is not None
    imported_at = record.imported_at
    node_ids = [n.id for n in get_ordered_nodes(db_session, note.id, user)]

    report = run_import(db_session, source, user)

    assert report.unchanged == 1
    assert report.refreshed == 0
    assert get_note_update_timestamp(db_session, note.id) == timestamp
    record = get_note_import(db_session, note.id)
    assert record is not None
    assert record.imported_at == imported_at
    assert [n.id for n in get_ordered_nodes(db_session, note.id, user)] == node_ids


def test_note_with_edited_node_is_kept_and_reported(db_session: Session) -> None:
    user = _make_user(db_session)
    run_import(db_session, _FakeImportSource({"NB/t.html": _doc("NB", "T", "v1")}), user)
    note = _note(db_session, "NB", "T")
    node = get_ordered_nodes(db_session, note.id, user)[0]
    update_markdown_node(db_session, node.id, user, "edited", "paragraph", node.version)
    db_session.commit()
    record = get_note_import(db_session, note.id)
    assert record is not None
    imported_at = record.imported_at
    modified_at = get_note_update_timestamp(db_session, note.id)

    report = run_import(
        db_session,
        _FakeImportSource({"NB/t.html": _doc("NB", "T", "v2")}),
        user,
    )

    assert report.refreshed == 0
    assert len(report.kept_modified) == 1
    kept = report.kept_modified[0]
    assert kept.note_id == note.id
    assert kept.notebook_id == note.notebook_id
    assert kept.title == "T"
    assert kept.notebook == "NB"
    assert kept.source_path == "NB/t.html"
    assert kept.imported_at == imported_at
    assert kept.modified_at == modified_at
    assert _payloads(db_session, note, user) == ["edited"]


def test_note_with_edited_title_is_kept_and_reported(db_session: Session) -> None:
    user = _make_user(db_session)
    run_import(db_session, _FakeImportSource({"NB/t.html": _doc("NB", "T", "v1")}), user)
    note = _note(db_session, "NB", "T")
    # Same title, so the dedup key still matches; the edit still touches the note.
    update_note(db_session, note.id, user, title="T")
    db_session.commit()

    report = run_import(
        db_session,
        _FakeImportSource({"NB/t.html": _doc("NB", "T", "v2")}),
        user,
    )

    assert [k.note_id for k in report.kept_modified] == [note.id]
    assert _payloads(db_session, note, user) == ["v1"]


def test_modified_note_is_kept_on_every_later_run(db_session: Session) -> None:
    user = _make_user(db_session)
    run_import(db_session, _FakeImportSource({"NB/t.html": _doc("NB", "T", "v1")}), user)
    note = _note(db_session, "NB", "T")
    add_markdown_node(db_session, note.id, user, "mine", "paragraph")
    db_session.commit()
    source = _FakeImportSource({"NB/t.html": _doc("NB", "T", "v1")})

    first = run_import(db_session, source, user)
    second = run_import(db_session, source, user)

    assert len(first.kept_modified) == 1
    assert len(second.kept_modified) == 1
    assert _payloads(db_session, note, user) == ["v1", "mine"]


def test_override_refreshes_modified_note_and_resets_tracking(
    db_session: Session,
) -> None:
    user = _make_user(db_session)
    run_import(db_session, _FakeImportSource({"NB/t.html": _doc("NB", "T", "v1")}), user)
    note = _note(db_session, "NB", "T")
    add_markdown_node(db_session, note.id, user, "mine", "paragraph")
    db_session.commit()

    report = run_import(
        db_session,
        _FakeImportSource({"NB/t.html": _doc("NB", "T", "v2")}),
        user,
        override=True,
    )

    assert report.refreshed == 1
    assert report.kept_modified == []
    assert _payloads(db_session, note, user) == ["v2"]
    record = get_note_import(db_session, note.id)
    assert record is not None
    assert record.imported_at == get_note_update_timestamp(db_session, note.id)


def test_deleted_imported_note_is_created_again(db_session: Session) -> None:
    user = _make_user(db_session)
    source = _FakeImportSource({"NB/t.html": _doc("NB", "T", "v1")})
    run_import(db_session, source, user)
    note = _note(db_session, "NB", "T")
    db_session.delete(note)
    db_session.commit()
    assert list(db_session.scalars(select(NoteImport))) == []

    report = run_import(db_session, source, user)

    assert report.created == 1
    assert _payloads(db_session, _note(db_session, "NB", "T"), user) == ["v1"]


# ---------------------------------------------------------------------------
# Untracked notes (imported before note_imports existed)
# ---------------------------------------------------------------------------


def _make_untracked_note(session: Session, user: User) -> Note:
    nb = create_notebook(session, "NB", user)
    note = create_note(session, nb.id, user, "T", external_id=compute_external_id("T"))
    add_markdown_node(session, note.id, user, "old", "paragraph")
    session.commit()
    return note


def test_untracked_note_is_kept_and_reported(db_session: Session) -> None:
    user = _make_user(db_session)
    note = _make_untracked_note(db_session, user)

    report = run_import(
        db_session,
        _FakeImportSource({"NB/t.html": _doc("NB", "T", "new")}),
        user,
    )

    assert [k.note_id for k in report.kept_untracked] == [note.id]
    assert report.kept_untracked[0].imported_at is None
    assert _payloads(db_session, note, user) == ["old"]
    assert get_note_import(db_session, note.id) is None


def test_override_refreshes_untracked_note_and_starts_tracking(
    db_session: Session,
) -> None:
    user = _make_user(db_session)
    note = _make_untracked_note(db_session, user)

    report = run_import(
        db_session,
        _FakeImportSource({"NB/t.html": _doc("NB", "T", "new")}),
        user,
        override=True,
    )

    assert report.refreshed == 1
    assert report.kept_untracked == []
    assert _payloads(db_session, note, user) == ["new"]
    record = get_note_import(db_session, note.id)
    assert record is not None
    assert record.source_path == "NB/t.html"


def test_override_on_identical_untracked_note_only_starts_tracking(
    db_session: Session,
) -> None:
    user = _make_user(db_session)
    note = _make_untracked_note(db_session, user)
    timestamp = get_note_update_timestamp(db_session, note.id)

    report = run_import(
        db_session,
        _FakeImportSource({"NB/t.html": _doc("NB", "T", "old")}),
        user,
        override=True,
    )

    assert report.unchanged == 1
    assert get_note_update_timestamp(db_session, note.id) == timestamp
    assert get_note_import(db_session, note.id) is not None


# ---------------------------------------------------------------------------
# Duplicate titles within one notebook (probe B)
# ---------------------------------------------------------------------------


def test_duplicate_title_in_one_notebook_keeps_first_and_reports_rest(
    db_session: Session,
) -> None:
    user = _make_user(db_session)
    source = _FakeImportSource(
        {
            "NB/Untitled (1).html": _doc("NB", "Untitled", "first"),
            "NB/Untitled (2).html": _doc("NB", "Untitled", "second"),
        },
    )

    first = run_import(db_session, source, user)
    second = run_import(db_session, source, user)

    for report in (first, second):
        assert [(d.title, d.notebook, d.source_path) for d in report.duplicate_title] == [
            ("Untitled", "NB", "NB/Untitled (2).html"),
        ]
    assert first.created == 1
    assert second.unchanged == 1
    assert second.refreshed == 0
    assert _payloads(db_session, _note(db_session, "NB", "Untitled"), user) == ["first"]


def test_two_notebooks_with_same_titled_note_dont_collide(db_session: Session) -> None:
    user = _make_user(db_session)
    source = _FakeImportSource(
        {
            "NB1/a.html": _doc("NB1", "Same Title"),
            "NB2/a.html": _doc("NB2", "Same Title"),
        },
    )

    report = run_import(db_session, source, user)

    assert report.created == 2
    assert report.duplicate_title == []
    notes = list(db_session.scalars(select(Note).where(Note.title == "Same Title")))
    assert len(notes) == 2
    assert notes[0].notebook_id != notes[1].notebook_id


# ---------------------------------------------------------------------------
# Notebook owned by another user (probe C)
# ---------------------------------------------------------------------------


def test_notebook_owned_by_another_user_is_skipped_and_reported(
    db_session: Session,
) -> None:
    other_owner = _make_user(db_session, "other@test.com")
    pre_existing = create_notebook(db_session, "Work", other_owner)
    db_session.commit()

    user = _make_user(db_session)
    report = run_import(db_session, HTMLFileImportSource(FIXTURES_DIR), user)

    assert len(report.notebooks_failed) == 1
    failed = report.notebooks_failed[0]
    assert failed.name == "Work"
    assert failed.skipped_notes == 2
    assert "another user" in failed.reason
    assert report.created == 1  # Personal still imports
    assert report.failed == []
    work_notebooks = list(
        db_session.scalars(select(Notebook).where(Notebook.name == "Work")),
    )
    assert [nb.id for nb in work_notebooks] == [pre_existing.id]
    assert work_notebooks[0].owner_id == other_owner.uid
    work_notes = db_session.scalars(
        select(Note).where(Note.notebook_id == pre_existing.id),
    )
    assert list(work_notes) == []


# ---------------------------------------------------------------------------
# web.clip skip
# ---------------------------------------------------------------------------


def test_web_clip_note_is_skipped_with_no_db_writes(db_session: Session) -> None:
    user = _make_user(db_session)
    source = _FakeImportSource(
        {
            "NB/clip.html": ImportedNote(
                notebook_name="NB",
                parsed=ParsedNote(title="", blocks=[], skip=True),
            ),
        },
    )

    report = run_import(db_session, source, user)

    assert report.skipped_web_clip == 1
    assert report.created == 0
    assert list(db_session.scalars(select(Notebook))) == []
    assert list(db_session.scalars(select(Note))) == []


def test_included_web_clip_is_imported_and_counted(db_session: Session) -> None:
    user = _make_user(db_session)
    source = _FakeImportSource(
        {
            "NB/clip.html": ImportedNote(
                notebook_name="NB",
                parsed=ParsedNote(
                    title="Clip",
                    blocks=[ParsedBlock("paragraph", "clipped")],
                    web_clip=True,
                ),
            ),
        },
    )

    report = run_import(db_session, source, user)

    assert report.created == 1
    assert report.imported_web_clip == 1
    assert report.skipped_web_clip == 0


def test_run_import_with_web_clips_included_from_fixtures(db_session: Session) -> None:
    user = _make_user(db_session)
    source = HTMLFileImportSource(FIXTURES_DIR, include_web_clips=True)

    report = run_import(db_session, source, user)

    assert report.created == 4
    assert report.skipped_web_clip == 0
    assert report.imported_web_clip == 1


# ---------------------------------------------------------------------------
# Deletion propagation — never
# ---------------------------------------------------------------------------


def test_removing_source_file_does_not_delete_previously_imported_note(
    tmp_path: Path,
    db_session: Session,
) -> None:
    user = _make_user(db_session)
    notebook_dir = tmp_path / "NB"
    notebook_dir.mkdir()
    note_path = notebook_dir / "note.html"
    note_path.write_text("<h1>Persisted Note</h1><p>content</p>")

    source = HTMLFileImportSource(tmp_path)
    run_import(db_session, source, user)
    assert len(list(db_session.scalars(select(Note)))) == 1

    note_path.unlink()

    report = run_import(db_session, source, user)

    assert report.created == 0
    notes = list(db_session.scalars(select(Note)))
    assert len(notes) == 1
    assert notes[0].title == "Persisted Note"


# ---------------------------------------------------------------------------
# Per-document resilience (probe A)
# ---------------------------------------------------------------------------


def test_one_broken_document_does_not_abort_the_whole_run(db_session: Session) -> None:
    user = _make_user(db_session)
    source = _RaisingImportSource(
        {
            "NB/good.html": _doc("NB", "Good Note"),
            "NB/bad.html": _doc("NB", "Bad Note"),
        },
        broken_id="NB/bad.html",
    )

    report = run_import(db_session, source, user)

    assert report.created == 1
    assert [(f.source_path, f.error) for f in report.failed] == [("NB/bad.html", "boom")]
    titles = {n.title for n in db_session.scalars(select(Note))}
    assert titles == {"Good Note"}


def test_failure_mid_note_rolls_back_the_partial_note(db_session: Session) -> None:
    user = _make_user(db_session)
    source = _FakeImportSource(
        {
            "NB/a.html": _doc("NB", "A", "a1", "a2"),
            "NB/b.html": _doc("NB", "B", "b1"),
        },
    )
    real_add = notes_import_module.add_markdown_node
    calls = {"n": 0}

    def flaky_add(*args: object, **kwargs: object) -> Node:
        calls["n"] += 1
        if calls["n"] == 2:  # A's second node
            msg = "disk full"
            raise RuntimeError(msg)
        return real_add(*args, **kwargs)  # type: ignore[arg-type]

    with patch.object(notes_import_module, "add_markdown_node", flaky_add):
        report = run_import(db_session, source, user)

    assert report.created == 1
    assert [f.source_path for f in report.failed] == ["NB/a.html"]
    titles = {n.title for n in db_session.scalars(select(Note))}
    assert titles == {"B"}
    assert len(list(db_session.scalars(select(NoteImport)))) == 1

    rerun = run_import(db_session, source, user)

    assert rerun.created == 1
    assert rerun.unchanged == 1
    assert _payloads(db_session, _note(db_session, "NB", "A"), user) == ["a1", "a2"]


def test_failure_in_a_new_notebook_rolls_back_the_notebook_too(
    db_session: Session,
) -> None:
    user = _make_user(db_session)
    source = _FakeImportSource(
        {
            "NB1/a.html": _doc("NB1", "A", "a1"),
            "NB2/b.html": _doc("NB2", "B", "b1"),
        },
    )
    real_add = notes_import_module.add_markdown_node
    calls = {"n": 0}

    def flaky_add(*args: object, **kwargs: object) -> Node:
        calls["n"] += 1
        if calls["n"] == 1:
            msg = "boom"
            raise RuntimeError(msg)
        return real_add(*args, **kwargs)  # type: ignore[arg-type]

    with patch.object(notes_import_module, "add_markdown_node", flaky_add):
        report = run_import(db_session, source, user)

    # NB1 was created in the rolled-back transaction, so it is gone too.
    assert {nb.name for nb in db_session.scalars(select(Notebook))} == {"NB2"}
    assert report.created == 1
    assert [f.source_path for f in report.failed] == ["NB1/a.html"]
