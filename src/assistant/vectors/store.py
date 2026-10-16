"""Reads and writes `assistant.note_chunk_embedding`, the pgvector table.

The table is created by hand in the add_vector_index migration and is not
part of the ORM metadata (SQLite tests can't represent `vector`); it is
described here as a standalone Core `Table`. Its layout is the one
langchain's `PGVectorStore` expects, so the agent can search it with
langchain (see `assistant.vectors.search`).

Writes go through the caller's SQLAlchemy session rather than
`PGVectorStore.add_documents`, which commits every row on its own: here a
note's chunks are replaced in the same transaction that records them as
indexed, so readers never see half a note.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector  # type: ignore[import-untyped]
from sqlalchemy import Column, Integer, MetaData, Table, Text, delete, insert, update
from sqlalchemy.dialects.postgresql import JSONB, UUID

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.orm import Session

    from assistant.vectors.chunking import NoteChunk

SCHEMA = "assistant"
TABLE_NAME = "note_chunk_embedding"
# Dimension of `text-embedding-3-small`, fixed by the migration. A model with
# a different dimension needs a new migration.
EMBEDDING_DIMENSIONS = 1536

# Columns langchain's PGVectorStore maps onto a Document.
ID_COLUMN = "langchain_id"
CONTENT_COLUMN = "content"
EMBEDDING_COLUMN = "embedding"
METADATA_JSON_COLUMN = "langchain_metadata"
METADATA_COLUMNS = ["note_id", "notebook_id", "chunk_index"]

note_chunk_embedding = Table(
    TABLE_NAME,
    MetaData(),
    Column(ID_COLUMN, UUID(as_uuid=True), primary_key=True),
    Column(CONTENT_COLUMN, Text, nullable=False),
    Column(EMBEDDING_COLUMN, Vector(EMBEDDING_DIMENSIONS), nullable=False),
    Column("note_id", UUID(as_uuid=True), nullable=False),
    Column("notebook_id", UUID(as_uuid=True), nullable=False),
    Column("chunk_index", Integer, nullable=False),
    Column(METADATA_JSON_COLUMN, JSONB, nullable=False),
    schema=SCHEMA,
)


class EmbeddingDimensionError(ValueError):
    """The embedding model returned vectors of the wrong size."""


def replace_note_chunks(
    session: Session,
    *,
    note_id: uuid.UUID,
    notebook_id: uuid.UUID,
    chunks: Sequence[NoteChunk],
    embeddings: Sequence[Sequence[float]],
) -> None:
    """Replace every stored chunk of a note with `chunks`.

    Args:
        session: Session whose transaction the change joins.
        note_id: The note.
        notebook_id: The note's notebook (stored for permission filters).
        chunks: The new chunks, see `assistant.vectors.chunking.chunk_note`.
        embeddings: One vector per chunk, in the same order.

    Raises:
        ValueError: If chunks and embeddings differ in number.
        EmbeddingDimensionError: If a vector is not `EMBEDDING_DIMENSIONS` long.
    """
    if len(chunks) != len(embeddings):
        msg = f"{len(chunks)} chunks but {len(embeddings)} embeddings"
        raise ValueError(msg)
    for vector in embeddings:
        if len(vector) != EMBEDDING_DIMENSIONS:
            msg = (
                f"Embedding has {len(vector)} dimensions, the table stores "
                f"{EMBEDDING_DIMENSIONS}"
            )
            raise EmbeddingDimensionError(msg)

    delete_note_chunks(session, note_id)
    if not chunks:
        return
    session.execute(
        insert(note_chunk_embedding),
        [
            {
                ID_COLUMN: uuid.uuid4(),
                CONTENT_COLUMN: chunk.text,
                EMBEDDING_COLUMN: list(vector),
                "note_id": note_id,
                "notebook_id": notebook_id,
                "chunk_index": chunk.index,
                METADATA_JSON_COLUMN: chunk.metadata,
            }
            for chunk, vector in zip(chunks, embeddings, strict=True)
        ],
    )


def update_note_chunk_metadata(
    session: Session,
    *,
    note_id: uuid.UUID,
    notebook_id: uuid.UUID,
    chunks: Sequence[NoteChunk],
) -> None:
    """Rewrite the metadata of a note's stored chunks, keeping their vectors.

    Used when the embedded text did not change but metadata did (e.g. the
    update timestamp). `chunks` must match the stored chunks one to one.
    """
    for chunk in chunks:
        session.execute(
            update(note_chunk_embedding)
            .where(
                note_chunk_embedding.c.note_id == note_id,
                note_chunk_embedding.c.chunk_index == chunk.index,
            )
            .values(
                {
                    "notebook_id": notebook_id,
                    METADATA_JSON_COLUMN: chunk.metadata,
                },
            ),
        )


def delete_note_chunks(session: Session, note_id: uuid.UUID) -> None:
    """Delete every stored chunk of a note."""
    session.execute(
        delete(note_chunk_embedding).where(note_chunk_embedding.c.note_id == note_id),
    )
