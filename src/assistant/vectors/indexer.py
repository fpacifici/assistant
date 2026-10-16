"""Embeds one note into `note_chunk_embedding`.

`VectorIndexer.index_note` renders the note to markdown, chunks it, and
compares a hash of the chunk texts with the one recorded at the last run:
if nothing that is embedded changed, only the chunk metadata is refreshed
and the embedding model is not called. Otherwise the note's chunks are
embedded and replaced. Either way the note's `NoteVectorIndex` row records
the time the note was *read*, so an edit committed while the model was
being called keeps the note stale (see `assistant.vectors.staleness`).

Nothing here commits: callers own the transaction.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import select

from assistant.config import Config
from assistant.models.schema import Node, Note, NoteVectorIndex
from assistant.vectors.chunking import NoteInfo, chunk_note
from assistant.vectors.markdown import note_markdown
from assistant.vectors.store import replace_note_chunks, update_note_chunk_metadata

if TYPE_CHECKING:
    import uuid

    from langchain_core.embeddings import Embeddings
    from sqlalchemy.orm import Session

    from assistant.vectors.chunking import NoteChunk

logger = logging.getLogger(__name__)

# Bump whenever chunking or rendering changes what gets embedded, then run
# `make reindex-vectors` (reindex_search --vectors --stale-only).
VECTOR_INDEX_VERSION = 1


class IndexOutcome(StrEnum):
    """What `VectorIndexer.index_note` did."""

    EMBEDDED = "embedded"
    UNCHANGED = "unchanged"
    MISSING = "missing"


def content_hash(model: str, chunks: list[NoteChunk]) -> str:
    """SHA-256 identifying what would be embedded, model included."""
    digest = hashlib.sha256(model.encode())
    for chunk in chunks:
        digest.update(b"\x1e")
        digest.update(chunk.text.encode())
    return digest.hexdigest()


class VectorIndexer:
    """Embeds notes with one embedding model."""

    def __init__(self, embeddings: Embeddings, model: str) -> None:
        """Create an indexer.

        Args:
            embeddings: The langchain embedding model.
            model: Its name, part of the content hash so a model change
                re-embeds notes.
        """
        self.embeddings = embeddings
        self.model = model

    def index_note(self, session: Session, note_id: uuid.UUID) -> IndexOutcome:
        """Bring one note's embeddings up to date.

        Args:
            session: Session to read the note and write the chunks with.
            note_id: The note to index.

        Returns:
            What was done; `MISSING` if the note no longer exists.

        Raises:
            Exception: Whatever the embedding model raises (no credits,
                rate limits, network); nothing is written in that case.
        """
        read_at = datetime.now(UTC)
        note = session.get(Note, note_id)
        if note is None:
            return IndexOutcome.MISSING

        nodes = session.scalars(
            select(Node).where(Node.note_id == note_id).order_by(Node.position),
        )
        info = NoteInfo(
            note_id=note.id,
            notebook_id=note.notebook_id,
            notebook_name=note.notebook.name,
            title=note.title,
            created_at=note.creation_timestamp,
            updated_at=note.update_timestamp,
        )
        chunks = chunk_note(
            info, note_markdown(nodes), index_version=VECTOR_INDEX_VERSION
        )
        new_hash = content_hash(self.model, chunks)

        entry = session.get(NoteVectorIndex, note_id)
        if (
            entry is not None
            and entry.indexed_at is not None
            and entry.index_version == VECTOR_INDEX_VERSION
            and entry.content_hash == new_hash
        ):
            update_note_chunk_metadata(
                session,
                note_id=note.id,
                notebook_id=note.notebook_id,
                chunks=chunks,
            )
            outcome = IndexOutcome.UNCHANGED
        else:
            vectors = self.embeddings.embed_documents([chunk.text for chunk in chunks])
            replace_note_chunks(
                session,
                note_id=note.id,
                notebook_id=note.notebook_id,
                chunks=chunks,
                embeddings=vectors,
            )
            outcome = IndexOutcome.EMBEDDED

        if entry is None:
            entry = NoteVectorIndex(note_id=note_id)
            session.add(entry)
        entry.content_hash = new_hash
        entry.index_version = VECTOR_INDEX_VERSION
        entry.indexed_at = read_at
        session.flush()
        logger.debug(
            "Note %s vector index: %s (%d chunks)", note_id, outcome, len(chunks)
        )
        return outcome


def create_vector_indexer(config: Config | None = None) -> VectorIndexer | None:
    """Build the indexer from config, or `None` when AI is disabled.

    AI is disabled when `OPENAI_API_KEY` is not set; nothing is embedded
    then and notes stay stale.
    """
    ai_config = (config or Config()).get_ai_config()
    if not ai_config["enabled"]:
        return None
    from langchain_openai import OpenAIEmbeddings  # noqa: PLC0415

    model = ai_config["embedding_model"]
    return VectorIndexer(OpenAIEmbeddings(model=model), model)
