"""The search service: one search string in, ranked notes with snippets out.

This is the stable interface the API (and later the agent and the TUI)
depend on. The engine behind it — Postgres full text search today — can
change without touching callers (see docs/adr/0002-postgres-fts-search.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import func, literal_column, select

from assistant.models.schema import Note
from assistant.search.analysis import analyze

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from sqlalchemy.sql.elements import ColumnClause

    from assistant.models.schema import User

# Generated Postgres-only columns, deliberately not mapped in the ORM.
_NOTE_VECTOR: ColumnClause[object] = literal_column("assistant.notes.search_vector")


@dataclass(frozen=True)
class SearchHit:
    """One matching note."""

    note: Note
    score: float


@dataclass(frozen=True)
class SearchResults:
    """A page of search hits."""

    hits: list[SearchHit]


def search(session: Session, caller: User, raw_query: str) -> SearchResults:
    """Search the notes `caller` can view."""
    del caller
    tsquery = " & ".join(f"'{term}'" for term in analyze(raw_query))
    query = func.to_tsquery(literal_column("'simple'::regconfig"), tsquery)
    rank = func.ts_rank_cd(_NOTE_VECTOR, query)
    stmt = select(Note, rank).where(_NOTE_VECTOR.op("@@")(query)).order_by(rank.desc())
    return SearchResults(
        hits=[SearchHit(note=note, score=score) for note, score in session.execute(stmt)],
    )
