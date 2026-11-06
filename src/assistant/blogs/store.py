"""Reads and writes `assistant.post_chunk_embedding`, the post vector table.

Postgres-only, created by hand in a migration and not part of the ORM
metadata, like `note_chunk_embedding` (see `assistant.vectors.store`, whose
layout it follows so langchain's `PGVectorStore` can search it). It is kept
apart from the notes so nothing that searches notes can reach a post. No
feature reads it yet.

Nothing here commits: callers own the transaction.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector  # type: ignore[import-untyped]
from sqlalchemy import Column, Integer, MetaData, Table, Text, delete, insert
from sqlalchemy.dialects.postgresql import JSONB, UUID

from assistant.vectors.store import (
    CONTENT_COLUMN,
    EMBEDDING_COLUMN,
    EMBEDDING_DIMENSIONS,
    ID_COLUMN,
    METADATA_JSON_COLUMN,
    SCHEMA,
    EmbeddingDimensionError,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.orm import Session

    from assistant.blogs.chunking import PostChunk

TABLE_NAME = "post_chunk_embedding"

post_chunk_embedding = Table(
    TABLE_NAME,
    MetaData(),
    Column(ID_COLUMN, UUID(as_uuid=True), primary_key=True),
    Column(CONTENT_COLUMN, Text, nullable=False),
    Column(EMBEDDING_COLUMN, Vector(EMBEDDING_DIMENSIONS), nullable=False),
    Column("post_id", UUID(as_uuid=True), nullable=False),
    Column("source_id", UUID(as_uuid=True), nullable=False),
    Column("owner_id", UUID(as_uuid=True), nullable=False),
    Column("chunk_index", Integer, nullable=False),
    Column(METADATA_JSON_COLUMN, JSONB, nullable=False),
    schema=SCHEMA,
)


def replace_post_chunks(  # noqa: PLR0913
    session: Session,
    *,
    post_id: uuid.UUID,
    source_id: uuid.UUID,
    owner_id: uuid.UUID,
    chunks: Sequence[PostChunk],
    embeddings: Sequence[Sequence[float]],
) -> None:
    """Replace every stored chunk of a post with `chunks`.

    Args:
        session: Session whose transaction the change joins.
        post_id: The post.
        source_id: Its source.
        owner_id: Its owner, stored so a search can filter on it.
        chunks: The new chunks, see `assistant.blogs.chunking.chunk_post`.
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

    delete_post_chunks(session, post_id)
    session.execute(
        insert(post_chunk_embedding),
        [
            {
                ID_COLUMN: uuid.uuid4(),
                CONTENT_COLUMN: chunk.text,
                EMBEDDING_COLUMN: list(vector),
                "post_id": post_id,
                "source_id": source_id,
                "owner_id": owner_id,
                "chunk_index": chunk.index,
                METADATA_JSON_COLUMN: chunk.metadata,
            }
            for chunk, vector in zip(chunks, embeddings, strict=True)
        ],
    )


def delete_post_chunks(session: Session, post_id: uuid.UUID) -> None:
    """Delete every stored chunk of a post."""
    session.execute(
        delete(post_chunk_embedding).where(post_chunk_embedding.c.post_id == post_id),
    )
