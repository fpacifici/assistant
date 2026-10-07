"""The search service: one search string in, ranked notes with snippets out.

This is the stable interface the API (and later the agent and the TUI)
depend on. The engine behind it — Postgres full text search today — can
change without touching callers (see docs/adr/0002-postgres-fts-search.md).

A note matches when all the query's words appear anywhere in it (title or
body). Its snippets are the blocks containing any of the words.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import exists, func, literal, literal_column, select

from assistant.models.schema import Node, Note, NoteTag, Tag
from assistant.notes.permissions import viewable_note_filter
from assistant.search.indexer import node_plain_text
from assistant.search.query import (
    SearchQuery,
    parse_query,
    to_any_word_tsquery,
    to_tsquery,
)
from assistant.search.snippets import SnippetSegment, build_segments

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence

    from sqlalchemy.orm import Session
    from sqlalchemy.sql.elements import ColumnClause, ColumnElement

    from assistant.models.schema import User

DEFAULT_LIMIT = 20
MAX_SNIPPETS_PER_NOTE = 3

# Generated Postgres-only columns, deliberately not mapped in the ORM.
_NOTE_VECTOR: ColumnClause[object] = literal_column("assistant.notes.search_vector")
_NODE_VECTOR: ColumnClause[object] = literal_column("assistant.nodes.search_vector")
_SIMPLE: ColumnClause[object] = literal_column("'simple'::regconfig")


class SearchSort(StrEnum):
    """Result ordering."""

    RELEVANCE = "relevance"
    UPDATED = "updated"


@dataclass(frozen=True)
class Snippet:
    """A matching block of a note, with the matched words highlighted."""

    node_id: uuid.UUID
    segments: tuple[SnippetSegment, ...]


@dataclass(frozen=True)
class SearchHit:
    """One matching note.

    `snippets` are up to `MAX_SNIPPETS_PER_NOTE` matching blocks in note
    order; when no block matched (a title-only or tag-only match) it is
    the note's first non-empty block, unhighlighted.
    """

    note: Note
    score: float
    title_segments: tuple[SnippetSegment, ...]
    snippets: tuple[Snippet, ...]


@dataclass(frozen=True)
class SearchResults:
    """A page of search hits.

    `unknown_tags` lists `tag:` filters naming a tag the caller doesn't
    have; any such filter makes the result empty.
    """

    hits: list[SearchHit]
    unknown_tags: list[str] = field(default_factory=list)


def search(  # noqa: PLR0913
    session: Session,
    caller: User,
    raw_query: str,
    *,
    offset: int = 0,
    limit: int = DEFAULT_LIMIT,
    sort: SearchSort | None = None,
) -> SearchResults:
    """Search the notes `caller` can view.

    Args:
        session: Database session (owned by the caller).
        caller: The user searching; only notes they can view are returned
            and `tag:` filters refer to their own tags.
        raw_query: The search string (syntax in docs/specs/0007-search.md).
        offset: Number of hits to skip.
        limit: Maximum number of hits to return.
        sort: Defaults to relevance, or to most recently updated for a
            query with only tags.

    Raises:
        EmptySearchQueryError: If `raw_query` has nothing to search for.
    """
    parsed = parse_query(raw_query)

    tag_ids: dict[str, uuid.UUID] = {}
    if parsed.tags:
        rows = session.execute(
            select(Tag.normalized_name, Tag.id).where(
                Tag.owner_id == caller.uid,
                Tag.normalized_name.in_(parsed.tags),
            ),
        )
        tag_ids = dict(rows.tuples().all())
        unknown = [key for key in parsed.tags if key not in tag_ids]
        if unknown:
            return SearchResults(hits=[], unknown_tags=unknown)

    tsquery = to_tsquery(parsed)
    query = func.to_tsquery(_SIMPLE, tsquery) if tsquery is not None else None
    rank: ColumnElement[float] = (
        func.ts_rank_cd(_NOTE_VECTOR, query) if query is not None else literal(0.0)
    )

    stmt = select(Note, rank).where(viewable_note_filter(caller))
    for tag_id in tag_ids.values():
        stmt = stmt.where(
            exists().where(NoteTag.note_id == Note.id, NoteTag.tag_id == tag_id)
        )
    if query is None:
        sort = SearchSort.UPDATED
    else:
        stmt = stmt.where(_NOTE_VECTOR.op("@@")(query))
    if sort != SearchSort.UPDATED:
        stmt = stmt.order_by(rank.desc())
    stmt = stmt.order_by(Note.update_timestamp.desc()).offset(offset).limit(limit)

    page = list(session.execute(stmt).tuples())
    snippets = _snippets(session, [note.id for note, _ in page], parsed)
    return SearchResults(
        hits=[
            SearchHit(
                note=note,
                score=score,
                title_segments=build_segments(note.title, parsed, width=len(note.title)),
                snippets=snippets.get(note.id, ()),
            )
            for note, score in page
        ],
    )


def _snippets(
    session: Session,
    note_ids: Sequence[uuid.UUID],
    parsed: SearchQuery,
) -> dict[uuid.UUID, tuple[Snippet, ...]]:
    """Snippets for each note: its best matching blocks, else its first block."""
    if not note_ids:
        return {}
    nodes: dict[uuid.UUID, list[Node]] = {}

    any_word = to_any_word_tsquery(parsed)
    if any_word is not None:
        query = func.to_tsquery(_SIMPLE, any_word)
        best = (
            func.row_number()
            .over(
                partition_by=Node.note_id,
                order_by=(func.ts_rank_cd(_NODE_VECTOR, query).desc(), Node.position),
            )
            .label("best")
        )
        ranked = (
            select(Node.id, best)
            .where(Node.note_id.in_(note_ids), _NODE_VECTOR.op("@@")(query))
            .subquery()
        )
        matching = session.scalars(
            select(Node)
            .join(ranked, ranked.c.id == Node.id)
            .where(ranked.c.best <= MAX_SNIPPETS_PER_NOTE)
            .order_by(Node.note_id, Node.position),
        )
        for node in matching:
            nodes.setdefault(node.note_id, []).append(node)

    unmatched = [note_id for note_id in note_ids if note_id not in nodes]
    if unmatched:
        first_blocks = session.scalars(
            select(Node)
            .where(Node.note_id.in_(unmatched), Node.search_text != "")
            .order_by(Node.note_id, Node.position)
            .distinct(Node.note_id),
        )
        for node in first_blocks:
            nodes[node.note_id] = [node]

    return {
        note_id: tuple(
            Snippet(
                node_id=node.id, segments=build_segments(node_plain_text(node), parsed)
            )
            for node in note_nodes
        )
        for note_id, note_nodes in nodes.items()
    }
