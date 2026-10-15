"""Tracks which notes need (re)embedding, and announces them after commit.

Embedding calls a remote model, so it never runs inside a write
transaction. Instead the notes service calls `mark_notes_stale` (or
`mark_notebook_stale`) as part of every write, which

1. sets `NoteVectorIndex.stale_since`, so the note is found by
   `stale_note_ids` (and `reindex_search --vectors --stale-only`) even if
   nobody embeds it now, and
2. remembers the note ids on the session; once the transaction commits they
   are handed to the registered listener (the API server's background
   worker, see `assistant.vectors.worker`). A rollback forgets them.

A note without a `NoteVectorIndex` row is stale by definition, so marking
only ever updates existing rows.

This module must not import `assistant.notes.service` (which imports it).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import and_, event, or_, select, update
from sqlalchemy.orm import Session

from assistant.models.schema import Note, NoteVectorIndex
from assistant.vectors.indexer import VECTOR_INDEX_VERSION

if TYPE_CHECKING:
    import uuid

    from sqlalchemy import Select

logger = logging.getLogger(__name__)

StaleListener = Callable[[list["uuid.UUID"]], None]

_SESSION_KEY = "assistant.vectors.stale_note_ids"
_listener: StaleListener | None = None


def set_stale_listener(listener: StaleListener | None) -> None:
    """Register the callable told about notes marked stale by a commit.

    There is one listener per process (the API server's worker); `None`
    unregisters it. Without a listener, stale notes simply wait for a
    reindex.
    """
    global _listener  # noqa: PLW0603
    _listener = listener


def _remember(session: Session, note_ids: Iterable[uuid.UUID]) -> None:
    pending: set[uuid.UUID] = session.info.setdefault(_SESSION_KEY, set())
    pending.update(note_ids)


def mark_notes_stale(session: Session, note_ids: Iterable[uuid.UUID]) -> None:
    """Record that these notes' embeddings no longer match their content."""
    ids = list(note_ids)
    if not ids:
        return
    session.execute(
        update(NoteVectorIndex)
        .where(NoteVectorIndex.note_id.in_(ids))
        .values(stale_since=datetime.now(UTC)),
    )
    _remember(session, ids)


def mark_notebook_stale(session: Session, notebook_id: uuid.UUID) -> None:
    """Mark every note of a notebook stale (its name is in their chunks)."""
    note_ids = list(
        session.scalars(select(Note.id).where(Note.notebook_id == notebook_id))
    )
    mark_notes_stale(session, note_ids)


def stale_note_ids() -> Select[tuple[uuid.UUID]]:
    """Query for the ids of notes whose embeddings are missing or outdated."""
    return (
        select(Note.id)
        .outerjoin(NoteVectorIndex, NoteVectorIndex.note_id == Note.id)
        .where(
            or_(
                NoteVectorIndex.note_id.is_(None),
                NoteVectorIndex.indexed_at.is_(None),
                NoteVectorIndex.index_version < VECTOR_INDEX_VERSION,
                and_(
                    NoteVectorIndex.stale_since.is_not(None),
                    NoteVectorIndex.stale_since > NoteVectorIndex.indexed_at,
                ),
            ),
        )
    )


@event.listens_for(Session, "after_commit")
def _announce_stale_notes(session: Session) -> None:
    pending: set[uuid.UUID] | None = session.info.pop(_SESSION_KEY, None)
    listener = _listener
    if not pending or listener is None:
        return
    try:
        listener(sorted(pending))
    except Exception:
        # The commit already happened; the notes stay stale for a reindex.
        logger.exception("Could not schedule %d notes for embedding", len(pending))


@event.listens_for(Session, "after_rollback")
def _forget_stale_notes(session: Session) -> None:
    session.info.pop(_SESSION_KEY, None)
