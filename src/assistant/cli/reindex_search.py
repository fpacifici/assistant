"""Rebuild the keyword search index.

Notes are indexed as they are written, so this is only needed after the
migration that adds the index (to backfill existing notes) and after a
change to `SEARCH_INDEX_VERSION` (with `--stale-only`).

Usage:
    python -m assistant.cli.reindex_search [--user-id UID] [--stale-only] [--batch-size N]
"""

from __future__ import annotations

import argparse
import logging
import sys
import uuid

from sqlalchemy import select

from assistant.models.database import get_session_factory
from assistant.models.schema import Note
from assistant.search.analysis import SEARCH_INDEX_VERSION
from assistant.search.indexer import index_note

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 200


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--user-id", type=uuid.UUID, help="Only notes owned by this user")
    parser.add_argument(
        "--stale-only",
        action="store_true",
        help="Only notes indexed with an older SEARCH_INDEX_VERSION",
    )
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Reindex notes, committing every `--batch-size` notes.

    Returns:
        0 on success, 1 on error.
    """
    args = _parse_args(argv)
    stmt = select(Note.id).order_by(Note.id)
    if args.user_id is not None:
        stmt = stmt.where(Note.owner_id == args.user_id)
    if args.stale_only:
        stmt = stmt.where(Note.search_index_version < SEARCH_INDEX_VERSION)
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


if __name__ == "__main__":
    sys.exit(main())
