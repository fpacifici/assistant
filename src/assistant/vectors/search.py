"""Semantic search over note chunks, restricted to what a user can view.

Searches `note_chunk_embedding` with langchain's v2 `PGVectorStore`. The
permission filter is a langchain metadata filter on the `notebook_id` and
`note_id` columns, computed from the user's entitlements on every query
(`assistant.notes.permissions.viewable_scope`), so sharing changes apply
immediately.

`PGVectorStore` runs on an async SQLAlchemy engine (psycopg 3) driven from
a background event loop, separate from the app's synchronous engine. HNSW
iterative scans are turned on for its connections, so a restrictive filter
keeps scanning the index instead of returning fewer than `k` chunks.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy.engine import make_url

from assistant.models.database import get_database_url
from assistant.notes.permissions import viewable_scope
from assistant.vectors.store import (
    CONTENT_COLUMN,
    EMBEDDING_COLUMN,
    ID_COLUMN,
    METADATA_COLUMNS,
    METADATA_JSON_COLUMN,
    SCHEMA,
    TABLE_NAME,
)

if TYPE_CHECKING:
    from langchain_core.embeddings import Embeddings
    from langchain_core.vectorstores import VectorStore
    from sqlalchemy.orm import Session

    from assistant.models.schema import User
    from assistant.notes.permissions import ViewableScope

DEFAULT_K = 6


@dataclass(frozen=True, slots=True)
class ChunkHit:
    """One matching chunk of a note the user can view."""

    note_id: uuid.UUID
    notebook_id: uuid.UUID
    title: str
    notebook_name: str
    content: str
    score: float


def scope_filter(scope: ViewableScope) -> dict[str, Any] | None:
    """The langchain metadata filter matching chunks of viewable notes.

    Returns:
        `None` when nothing is viewable (there is nothing to search).
    """
    clauses: list[dict[str, Any]] = []
    if scope.notebook_ids:
        clauses.append({"notebook_id": {"$in": sorted(map(str, scope.notebook_ids))}})
    if scope.note_ids:
        clauses.append({"note_id": {"$in": sorted(map(str, scope.note_ids))}})
    if not clauses:
        return None
    return clauses[0] if len(clauses) == 1 else {"$or": clauses}


def async_database_url() -> str:
    """The app's database URL with the psycopg 3 driver, for async engines."""
    return (
        make_url(get_database_url())
        .set(drivername="postgresql+psycopg")
        .render_as_string(
            hide_password=False,
        )
    )


def create_vector_store(embeddings: Embeddings) -> VectorStore:
    """A langchain `PGVectorStore` over `note_chunk_embedding`."""
    from langchain_postgres import PGEngine, PGVectorStore  # noqa: PLC0415

    engine = PGEngine.from_connection_string(
        async_database_url(),
        connect_args={"options": "-c hnsw.iterative_scan=strict_order"},
    )
    return PGVectorStore.create_sync(
        engine,
        embeddings,
        TABLE_NAME,
        schema_name=SCHEMA,
        content_column=CONTENT_COLUMN,
        embedding_column=EMBEDDING_COLUMN,
        metadata_columns=METADATA_COLUMNS,
        id_column=ID_COLUMN,
        metadata_json_column=METADATA_JSON_COLUMN,
    )


class NoteSearcher:
    """Finds the chunks closest to a query among the notes a user can view."""

    def __init__(self, embeddings: Embeddings) -> None:
        """Create a searcher; the store is built on first use.

        Args:
            embeddings: The model the chunks were embedded with.
        """
        self._embeddings = embeddings
        self._store: VectorStore | None = None
        self._lock = threading.Lock()

    @property
    def store(self) -> VectorStore:
        """The underlying langchain vector store."""
        with self._lock:
            if self._store is None:
                self._store = create_vector_store(self._embeddings)
            return self._store

    def search(
        self,
        session: Session,
        user: User,
        query: str,
        *,
        k: int = DEFAULT_K,
    ) -> list[ChunkHit]:
        """Search the chunks of every note `user` can view.

        Args:
            session: Used to read the user's entitlements.
            user: The user asking.
            query: Free text.
            k: Maximum number of chunks.

        Returns:
            The closest chunks, best first. `score` is the cosine distance
            (lower is closer).
        """
        where = scope_filter(viewable_scope(session, user))
        if where is None:
            return []
        results = self.store.similarity_search_with_score(query, k=k, filter=where)
        return [
            ChunkHit(
                note_id=uuid.UUID(str(doc.metadata["note_id"])),
                notebook_id=uuid.UUID(str(doc.metadata["notebook_id"])),
                title=str(doc.metadata.get("title", "")),
                notebook_name=str(doc.metadata.get("notebook_name", "")),
                content=doc.page_content,
                score=float(score),
            )
            for doc, score in results
        ]
