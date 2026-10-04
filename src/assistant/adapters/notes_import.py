"""Notes-import pipeline: drives an ImportSource, writes through notes/service.py.

Mirrors `dataload.py`'s shape, but for one-shot bulk import into the notes
system (Notebook/Note/Node) rather than incremental sync into the RAG
Document/vector-store pipeline.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from assistant.models.schema import PermissionName
from assistant.notes.permissions import notebook_permissions
from assistant.notes.service import (
    add_markdown_node,
    create_note,
    find_or_create_notebook,
    get_note_by_external_id,
    get_note_import,
    get_note_update_timestamp,
    get_ordered_nodes,
    record_note_import,
    replace_markdown_nodes,
)

if TYPE_CHECKING:
    import uuid
    from datetime import datetime

    from sqlalchemy.orm import Session

    from assistant.adapters.import_source import ImportedNote, ImportSource
    from assistant.models.schema import Note, User

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class KeptNote:
    """An existing note the import left untouched, so the user can review it.

    `imported_at` is None for a note with no import record (imported before
    tracking existed).
    """

    note_id: uuid.UUID
    notebook_id: uuid.UUID
    title: str
    notebook: str
    source_path: str
    imported_at: datetime | None
    modified_at: datetime


@dataclass(frozen=True, slots=True)
class DuplicateNote:
    """A document skipped because an earlier one in the run had the same title."""

    title: str
    notebook: str
    source_path: str


@dataclass(frozen=True, slots=True)
class FailedNote:
    """A document whose import raised; its writes were rolled back."""

    source_path: str
    error: str


@dataclass(slots=True)
class FailedNotebook:
    """A notebook the importing user cannot add notes to; all its notes skipped."""

    name: str
    reason: str
    skipped_notes: int = 0


@dataclass(slots=True)
class ImportReport:
    """Outcome of one `run_import` call: a count or a list per outcome."""

    notebooks_touched: int = 0
    created: int = 0
    refreshed: int = 0
    unchanged: int = 0
    skipped_web_clip: int = 0
    imported_web_clip: int = 0  # web clips created or refreshed
    kept_modified: list[KeptNote] = field(default_factory=list)
    kept_untracked: list[KeptNote] = field(default_factory=list)
    duplicate_title: list[DuplicateNote] = field(default_factory=list)
    failed: list[FailedNote] = field(default_factory=list)
    notebooks_failed: list[FailedNotebook] = field(default_factory=list)


def compute_external_id(title: str) -> str:
    """Hash a note's title.

    Dedup uniqueness comes from pairing this with notebook_id at the query
    level, not from this hash alone.

    Args:
        title: The note's resolved title.

    Returns:
        A hex-encoded SHA-256 digest of the title.
    """
    return hashlib.sha256(title.encode("utf-8")).hexdigest()


def run_import(
    session: Session,
    import_source: ImportSource,
    owner: User,
    *,
    override: bool = False,
) -> ImportReport:
    """Import every document available from `import_source` as a Note.

    Notes are matched by title within their notebook. For an existing match:

    - imported earlier and not edited since: refreshed with the new content
      (or left alone if the content is identical, so a re-run writes nothing);
    - edited since it was imported, or never tracked: left alone and listed
      in the report (`kept_modified` / `kept_untracked`).

    Only the first document per (notebook, title) in `list_documents` order
    is imported; later ones are reported as `duplicate_title`. Notebooks the
    owner cannot add notes to (an existing notebook with the same name owned
    by someone else) are skipped and reported.

    Commits per note, so a crash mid-run leaves already-imported notes durably
    in place. A failing note is rolled back entirely and reported. Never
    deletes a Note or its nodes.

    Args:
        session: Database session.
        import_source: Source to list and fetch documents from.
        owner: User who will own every notebook/note created by this run.
        override: If True, also refresh notes that were edited after their
            import or that have no import record.

    Returns:
        The import report.
    """
    report = ImportReport()
    notebooks_touched: set[str] = set()
    failed_notebooks: dict[str, FailedNotebook] = {}
    seen_keys: set[tuple[str, str]] = set()

    for document_id in import_source.list_documents():
        try:
            imported = import_source.get_note(document_id)

            if imported.parsed.skip:
                report.skipped_web_clip += 1
                continue

            name = imported.notebook_name
            failed_notebook = failed_notebooks.get(name)
            if failed_notebook is None:
                failed_notebook = _check_notebook_writable(session, name, owner)
                if failed_notebook is not None:
                    failed_notebooks[name] = failed_notebook
                    report.notebooks_failed.append(failed_notebook)
            if failed_notebook is not None:
                failed_notebook.skipped_notes += 1
                continue

            key = (name, imported.parsed.title)
            if key in seen_keys:
                report.duplicate_title.append(
                    DuplicateNote(imported.parsed.title, name, document_id),
                )
                continue
            seen_keys.add(key)

            _import_document(session, imported, document_id, owner, override, report)
            session.commit()
            notebooks_touched.add(name)
        except Exception as exc:
            session.rollback()
            logger.exception("Error processing document %s", document_id)
            report.failed.append(FailedNote(document_id, str(exc)))

    report.notebooks_touched = len(notebooks_touched)
    return report


def _check_notebook_writable(
    session: Session,
    name: str,
    owner: User,
) -> FailedNotebook | None:
    """Create the notebook if missing; report it if the owner can't add notes."""
    notebook = find_or_create_notebook(session, name, owner)
    if PermissionName.CREATE_NOTES in notebook_permissions(session, owner, notebook.id):
        return None
    # Notebook names are globally unique, so this is someone else's notebook.
    session.rollback()
    return FailedNotebook(
        name=name,
        reason="A notebook with this name belongs to another user",
    )


def _import_document(  # noqa: PLR0913
    session: Session,
    imported: ImportedNote,
    source_path: str,
    owner: User,
    override: bool,
    report: ImportReport,
) -> None:
    """Create, refresh or keep one note, and record the outcome in `report`.

    Does not commit; the caller commits or rolls back.
    """
    parsed = imported.parsed
    notebook = find_or_create_notebook(session, imported.notebook_name, owner)
    external_id = compute_external_id(parsed.title)
    blocks = [(b.block_type, b.payload) for b in parsed.blocks]
    existing = get_note_by_external_id(session, notebook.id, external_id)

    if existing is None:
        note = create_note(
            session,
            notebook.id,
            owner,
            parsed.title,
            external_id=external_id,
        )
        for block_type, payload in blocks:
            add_markdown_node(session, note.id, owner, payload, block_type)
        record_note_import(session, note.id, source_path)
        report.created += 1
        report.imported_web_clip += parsed.web_clip
        return

    record = get_note_import(session, existing.id)
    modified_at = get_note_update_timestamp(session, existing.id)
    edited = record is None or modified_at > record.imported_at
    if edited and not override:
        kept = KeptNote(
            note_id=existing.id,
            notebook_id=notebook.id,
            title=existing.title,
            notebook=notebook.name,
            source_path=source_path,
            imported_at=record.imported_at if record is not None else None,
            modified_at=modified_at,
        )
        (report.kept_untracked if record is None else report.kept_modified).append(kept)
        return

    if _stored_blocks(session, existing, owner) == blocks:
        if edited:
            # Override with nothing to write: just start tracking from here.
            record_note_import(session, existing.id, source_path)
        report.unchanged += 1
        return

    replace_markdown_nodes(session, existing.id, owner, blocks)
    record_note_import(session, existing.id, source_path)
    report.refreshed += 1
    report.imported_web_clip += parsed.web_clip


def _stored_blocks(session: Session, note: Note, owner: User) -> list[tuple[str, str]]:
    """The note's nodes as ordered (block_type, payload) pairs, like parsed blocks."""
    return [
        (node.block_type or "", node.payload or "")
        for node in get_ordered_nodes(session, note.id, owner)
    ]
