"""Notes-import pipeline: drives an ImportSource, writes through notes/service.py.

Mirrors `dataload.py`'s shape, but for one-shot bulk import into the notes
system (Notebook/Note/Node) rather than incremental sync into the RAG
Document/vector-store pipeline.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from assistant.notes.service import (
    add_markdown_node,
    create_note,
    find_or_create_notebook,
    get_note_by_external_id,
    replace_markdown_nodes,
)

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session

    from assistant.adapters.import_source import ImportSource

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ImportStats:
    """Summary counters for one `run_import` call."""

    notebooks_touched: int
    notes_created: int
    notes_skipped_existing: int
    notes_skipped_web_clip: int
    notes_overridden: int


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
    owner_id: uuid.UUID,
    *,
    override: bool = False,
) -> ImportStats:
    """Import every document available from `import_source` as a Note.

    Commits per note so a crash mid-run leaves already-imported notes durably
    in place, and a re-run naturally resumes (already-imported notes are
    skipped as duplicates). Never deletes a Note/its nodes.

    Args:
        session: Database session.
        import_source: Source to list and fetch documents from.
        owner_id: User who will own every notebook/note created by this run.
        override: If True, wholesale-replace already-imported notes' nodes
            with freshly parsed content instead of skipping them.

    Returns:
        Summary counters for the run.
    """
    notebooks_touched: set[str] = set()
    notes_created = 0
    notes_skipped_existing = 0
    notes_skipped_web_clip = 0
    notes_overridden = 0

    for document_id in import_source.list_documents():
        try:
            imported = import_source.get_note(document_id)

            if imported.parsed.skip:
                notes_skipped_web_clip += 1
                continue

            notebook = find_or_create_notebook(session, imported.notebook_name, owner_id)
            notebooks_touched.add(imported.notebook_name)

            external_id = compute_external_id(imported.parsed.title)
            existing = get_note_by_external_id(session, notebook.id, external_id)
            blocks = [(b.block_type, b.payload) for b in imported.parsed.blocks]

            if existing is None:
                note = create_note(
                    session,
                    notebook.id,
                    owner_id,
                    imported.parsed.title,
                    external_id=external_id,
                )
                for block_type, payload in blocks:
                    add_markdown_node(session, note.id, owner_id, payload, block_type)
                session.commit()
                notes_created += 1
            elif override:
                replace_markdown_nodes(session, existing.id, owner_id, blocks)
                session.commit()
                notes_overridden += 1
            else:
                notes_skipped_existing += 1
        except Exception:
            logger.exception("Error processing document %s", document_id)

    return ImportStats(
        notebooks_touched=len(notebooks_touched),
        notes_created=notes_created,
        notes_skipped_existing=notes_skipped_existing,
        notes_skipped_web_clip=notes_skipped_web_clip,
        notes_overridden=notes_overridden,
    )
