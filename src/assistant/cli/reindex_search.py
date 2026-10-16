"""Rebuild the keyword search index, or the note embeddings with --vectors.

Notes are indexed as they are written, so this is only needed after the
migration that adds an index (to backfill existing notes), after a change
to `SEARCH_INDEX_VERSION` / `VECTOR_INDEX_VERSION` (with `--stale-only`),
and, for embeddings, to retry notes whose embedding failed (e.g. no OpenAI
credits left) or that were written while the API server was not running.

Usage:
    python -m assistant.cli.reindex_search [--vectors] [--user-id UID]
        [--stale-only] [--batch-size N] [--delay-ms MS]
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import or_, select

from assistant.models.database import get_session_factory
from assistant.models.schema import Note, NoteSearchIndex
from assistant.search.analysis import SEARCH_INDEX_VERSION
from assistant.search.indexer import index_note
from assistant.vectors.indexer import create_vector_indexer
from assistant.vectors.staleness import stale_note_ids

if TYPE_CHECKING:
    from sqlalchemy import Select

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 200
# Pause between two embedded notes, to stay under the embedding API's rate limit.
DEFAULT_DELAY_MS = 250


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--vectors",
        action="store_true",
        help="Embed notes into the vector index instead (needs OPENAI_API_KEY)",
    )
    parser.add_argument("--user-id", type=uuid.UUID, help="Only notes owned by this user")
    parser.add_argument(
        "--stale-only",
        action="store_true",
        help="Only notes not indexed yet, changed since, or indexed with an older "
        "index version",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Keyword index only: notes per commit",
    )
    parser.add_argument(
        "--delay-ms",
        type=int,
        default=DEFAULT_DELAY_MS,
        help="--vectors only: milliseconds to wait between two notes "
        f"(default {DEFAULT_DELAY_MS}, 0 to disable)",
    )
    return parser.parse_args(argv)


def _keyword_stmt(args: argparse.Namespace) -> Select[tuple[uuid.UUID]]:
    stmt = select(Note.id)
    if args.stale_only:
        # Not indexed yet (no entry), or indexed with an older version.
        stmt = stmt.outerjoin(NoteSearchIndex, NoteSearchIndex.note_id == Note.id).where(
            or_(
                NoteSearchIndex.note_id.is_(None),
                NoteSearchIndex.index_version < SEARCH_INDEX_VERSION,
            ),
        )
    return stmt


def _reindex_keywords(args: argparse.Namespace, stmt: Select[tuple[uuid.UUID]]) -> int:
    try:
        with get_session_factory()() as session:
            note_ids = list(session.scalars(stmt))
            logger.info("Reindexing %d notes", len(note_ids))
            for done, note_id in enumerate(note_ids, start=1):
                index_note(session, note_id)
                if done % args.batch_size == 0:
                    session.commit()
                    logger.info("Reindexed %d/%d notes", done, len(note_ids))
            session.commit()
    except Exception:
        logger.exception("Failed to reindex notes")
        return 1
    logger.info("Reindexed %d notes", len(note_ids))
    return 0


def _reindex_vectors(stmt: Select[tuple[uuid.UUID]], delay_ms: int) -> int:
    """Embed each note in its own transaction; failures are logged and skipped.

    Waits `delay_ms` between two notes, so a large reindex does not hit the
    embedding API's rate limit.
    """
    indexer = create_vector_indexer()
    if indexer is None:
        logger.error("AI is disabled: set OPENAI_API_KEY to embed notes")
        return 1
    session_factory = get_session_factory()
    with session_factory() as session:
        note_ids = list(session.scalars(stmt))
    logger.info("Embedding %d notes", len(note_ids))
    failed = 0
    for done, note_id in enumerate(note_ids, start=1):
        if done > 1 and delay_ms > 0:
            time.sleep(delay_ms / 1000)
        try:
            with session_factory() as session:
                indexer.index_note(session, note_id)
                session.commit()
        except Exception:
            failed += 1
            logger.warning("Could not embed note %s", note_id, exc_info=True)
        if done % 50 == 0:
            logger.info("Embedded %d/%d notes", done, len(note_ids))
    if failed:
        logger.error("%d of %d notes could not be embedded", failed, len(note_ids))
        return 1
    logger.info("Embedded %d notes", len(note_ids))
    return 0


def main(argv: list[str] | None = None) -> int:
    """Reindex notes.

    Returns:
        0 on success, 1 on error (for --vectors: if any note failed).
    """
    args = _parse_args(argv)
    if args.vectors:
        stmt = stale_note_ids() if args.stale_only else select(Note.id)
    else:
        stmt = _keyword_stmt(args)
    if args.user_id is not None:
        stmt = stmt.where(Note.owner_id == args.user_id)
    stmt = stmt.order_by(Note.id)
    if args.vectors:
        return _reindex_vectors(stmt, args.delay_ms)
    return _reindex_keywords(args, stmt)


if __name__ == "__main__":
    sys.exit(main())
