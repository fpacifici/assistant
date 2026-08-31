"""Tests for the notes-import pipeline (`run_import`).

Real `db_session` fixture (SQLite) + a real fixture directory driven through
the real `HTMLFileImportSource`, plus a small in-memory fake `ImportSource`
for cases that need to isolate pipeline logic (dedup/override/error
resilience) from the filesystem.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from assistant.adapters.html_parser import ParsedBlock, ParsedNote
from assistant.adapters.import_source import ImportedNote, ImportSource
from assistant.adapters.notes_import import compute_external_id, run_import
from assistant.adapters.plugins.html_file import HTMLFileImportSource
from assistant.models.schema import Node, Note, Notebook, User
from assistant.notes.service import (
    create_notebook,
    get_note_by_external_id,
    get_ordered_nodes,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "html_import"


def _make_user(session: Session, email: str = "importer@test.com") -> User:
    user = User(email=email, firstname="A", lastname="B")
    session.add(user)
    session.flush()
    return user


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

    stats = run_import(db_session, source, user.uid)

    assert stats.notes_created == 3
    assert stats.notes_skipped_web_clip == 1
    assert stats.notes_skipped_existing == 0
    assert stats.notes_overridden == 0
    assert stats.notebooks_touched == 2

    notebooks = {nb.name for nb in db_session.scalars(select(Notebook))}
    assert notebooks == {"Work", "Personal"}

    notes = list(db_session.scalars(select(Note)))
    assert len(notes) == 3
    titles = {n.title for n in notes}
    assert titles == {"First Note", "Second Note"}  # "First Note" appears twice


def test_run_import_preserves_block_order_and_types(db_session: Session) -> None:
    user = _make_user(db_session)
    source = HTMLFileImportSource(FIXTURES_DIR)
    run_import(db_session, source, user.uid)

    work = db_session.scalar(select(Notebook).where(Notebook.name == "Work"))
    assert work is not None
    external_id = compute_external_id("First Note")
    note = get_note_by_external_id(db_session, work.id, external_id)
    assert note is not None

    nodes = get_ordered_nodes(db_session, note.id)
    assert [(n.block_type, n.payload) for n in nodes] == [
        ("paragraph", "This is the first paragraph."),
        ("heading", "## A subsection"),
        ("list_item", "- Item one"),
        ("list_item", "- Item two"),
    ]


def test_run_import_ignores_files_nested_too_deep(db_session: Session) -> None:
    user = _make_user(db_session)
    source = HTMLFileImportSource(FIXTURES_DIR)
    run_import(db_session, source, user.uid)

    titles = {n.title for n in db_session.scalars(select(Note))}
    assert "Too deep" not in titles


def test_run_import_reuses_existing_notebook_by_name(db_session: Session) -> None:
    other_owner = _make_user(db_session, "other@test.com")
    pre_existing = create_notebook(db_session, "Work", other_owner.uid)

    user = _make_user(db_session)
    source = HTMLFileImportSource(FIXTURES_DIR)
    run_import(db_session, source, user.uid)

    work_notebooks = list(
        db_session.scalars(select(Notebook).where(Notebook.name == "Work")),
    )
    assert len(work_notebooks) == 1
    assert work_notebooks[0].id == pre_existing.id
    assert work_notebooks[0].owner_id == other_owner.uid


def test_second_run_without_override_creates_no_duplicates(db_session: Session) -> None:
    user = _make_user(db_session)
    source = HTMLFileImportSource(FIXTURES_DIR)
    run_import(db_session, source, user.uid)

    notes_after_first = list(db_session.scalars(select(Note)))
    nodes_after_first = list(db_session.scalars(select(Node)))

    stats = run_import(db_session, source, user.uid)

    assert stats.notes_created == 0
    assert stats.notes_skipped_existing == 3
    notes_after_second = list(db_session.scalars(select(Note)))
    nodes_after_second = list(db_session.scalars(select(Node)))
    assert len(notes_after_second) == len(notes_after_first)
    assert len(nodes_after_second) == len(nodes_after_first)


# ---------------------------------------------------------------------------
# Override semantics (fake ImportSource, single controlled document)
# ---------------------------------------------------------------------------


def test_override_replaces_node_content_keeps_same_note_and_notebook_id(
    db_session: Session,
) -> None:
    user = _make_user(db_session)
    v1 = _FakeImportSource(
        {
            "doc1": ImportedNote(
                notebook_name="NB",
                parsed=ParsedNote(title="T", blocks=[ParsedBlock("paragraph", "v1")]),
            ),
        },
    )
    run_import(db_session, v1, user.uid)

    notebook = db_session.scalar(select(Notebook).where(Notebook.name == "NB"))
    assert notebook is not None
    external_id = compute_external_id("T")
    original_note = get_note_by_external_id(db_session, notebook.id, external_id)
    assert original_note is not None
    original_note_id = original_note.id
    original_notebook_id = original_note.notebook_id

    v2 = _FakeImportSource(
        {
            "doc1": ImportedNote(
                notebook_name="NB",
                parsed=ParsedNote(title="T", blocks=[ParsedBlock("paragraph", "v2")]),
            ),
        },
    )
    stats = run_import(db_session, v2, user.uid, override=True)

    assert stats.notes_overridden == 1
    assert stats.notes_created == 0

    reloaded = db_session.get(Note, original_note_id)
    assert reloaded is not None
    assert reloaded.id == original_note_id
    assert reloaded.notebook_id == original_notebook_id
    nodes = get_ordered_nodes(db_session, original_note_id)
    assert [n.payload for n in nodes] == ["v2"]


def test_without_override_existing_note_is_left_untouched(db_session: Session) -> None:
    user = _make_user(db_session)
    v1 = _FakeImportSource(
        {
            "doc1": ImportedNote(
                notebook_name="NB",
                parsed=ParsedNote(title="T", blocks=[ParsedBlock("paragraph", "v1")]),
            ),
        },
    )
    run_import(db_session, v1, user.uid)

    v2 = _FakeImportSource(
        {
            "doc1": ImportedNote(
                notebook_name="NB",
                parsed=ParsedNote(title="T", blocks=[ParsedBlock("paragraph", "v2")]),
            ),
        },
    )
    stats = run_import(db_session, v2, user.uid, override=False)

    assert stats.notes_skipped_existing == 1
    notebook = db_session.scalar(select(Notebook).where(Notebook.name == "NB"))
    assert notebook is not None
    note = get_note_by_external_id(db_session, notebook.id, compute_external_id("T"))
    assert note is not None
    nodes = get_ordered_nodes(db_session, note.id)
    assert [n.payload for n in nodes] == ["v1"]


# ---------------------------------------------------------------------------
# Dedup key is scoped per notebook
# ---------------------------------------------------------------------------


def test_two_notebooks_with_same_titled_note_dont_collide(db_session: Session) -> None:
    user = _make_user(db_session)
    source = _FakeImportSource(
        {
            "doc1": ImportedNote(
                notebook_name="NB1",
                parsed=ParsedNote(title="Same Title", blocks=[]),
            ),
            "doc2": ImportedNote(
                notebook_name="NB2",
                parsed=ParsedNote(title="Same Title", blocks=[]),
            ),
        },
    )

    stats = run_import(db_session, source, user.uid)

    assert stats.notes_created == 2
    notes = list(db_session.scalars(select(Note).where(Note.title == "Same Title")))
    assert len(notes) == 2
    assert notes[0].notebook_id != notes[1].notebook_id


# ---------------------------------------------------------------------------
# web.clip skip
# ---------------------------------------------------------------------------


def test_web_clip_note_is_skipped_with_no_db_writes(db_session: Session) -> None:
    user = _make_user(db_session)
    source = _FakeImportSource(
        {
            "doc1": ImportedNote(
                notebook_name="NB",
                parsed=ParsedNote(title="", blocks=[], skip=True),
            ),
        },
    )

    stats = run_import(db_session, source, user.uid)

    assert stats.notes_skipped_web_clip == 1
    assert stats.notes_created == 0
    assert list(db_session.scalars(select(Notebook))) == []
    assert list(db_session.scalars(select(Note))) == []


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
    run_import(db_session, source, user.uid)
    assert len(list(db_session.scalars(select(Note)))) == 1

    note_path.unlink()

    stats = run_import(db_session, source, user.uid)

    assert stats.notes_created == 0
    notes = list(db_session.scalars(select(Note)))
    assert len(notes) == 1
    assert notes[0].title == "Persisted Note"


# ---------------------------------------------------------------------------
# Per-document resilience
# ---------------------------------------------------------------------------


def test_one_broken_document_does_not_abort_the_whole_run(db_session: Session) -> None:
    user = _make_user(db_session)
    source = _RaisingImportSource(
        {
            "good": ImportedNote(
                notebook_name="NB",
                parsed=ParsedNote(title="Good Note", blocks=[]),
            ),
            "bad": ImportedNote(
                notebook_name="NB",
                parsed=ParsedNote(title="Bad Note", blocks=[]),
            ),
        },
        broken_id="bad",
    )

    stats = run_import(db_session, source, user.uid)

    assert stats.notes_created == 1
    titles = {n.title for n in db_session.scalars(select(Note))}
    assert titles == {"Good Note"}
