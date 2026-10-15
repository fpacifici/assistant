"""Tests for embedding notes into note_chunk_embedding (against Postgres)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding
from sqlalchemy import func, select

from assistant.models.schema import NoteVectorIndex, User
from assistant.notes.service import (
    add_markdown_node,
    create_note,
    create_notebook,
    delete_note,
    update_notebook,
)
from assistant.vectors.indexer import (
    VECTOR_INDEX_VERSION,
    IndexOutcome,
    VectorIndexer,
    create_vector_indexer,
)
from assistant.vectors.staleness import stale_note_ids
from assistant.vectors.store import (
    EMBEDDING_DIMENSIONS,
    EmbeddingDimensionError,
    note_chunk_embedding,
)

if TYPE_CHECKING:
    from sqlalchemy.engine import RowMapping
    from sqlalchemy.orm import Session

    from assistant.models.schema import Note

pytestmark = pytest.mark.postgres


class CountingEmbeddings(DeterministicFakeEmbedding):
    """Fake embeddings that count how many texts were embedded."""

    calls: int = 0

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls += len(texts)
        return super().embed_documents(texts)


@pytest.fixture
def embeddings() -> CountingEmbeddings:
    return CountingEmbeddings(size=EMBEDDING_DIMENSIONS)


@pytest.fixture
def indexer(embeddings: CountingEmbeddings) -> VectorIndexer:
    return VectorIndexer(embeddings, "fake-model")


def _user(session: Session) -> User:
    user = User(email=f"{uuid.uuid4()}@test.com", firstname="A", lastname="B")
    session.add(user)
    session.flush()
    return user


def _note(session: Session, owner: User, *paragraphs: str) -> Note:
    notebook = create_notebook(session, f"Travel {uuid.uuid4()}", owner)
    note = create_note(session, notebook_id=notebook.id, owner=owner, title="Rome")
    for text in paragraphs:
        add_markdown_node(session, note.id, owner, text, "paragraph")
    return note


def _rows(session: Session, note_id: uuid.UUID) -> list[RowMapping]:
    return list(
        session.execute(
            select(note_chunk_embedding)
            .where(note_chunk_embedding.c.note_id == note_id)
            .order_by(note_chunk_embedding.c.chunk_index),
        ).mappings(),
    )


# --- Embedding ---


def test_embeds_the_note_into_chunks(
    pg_session: Session,
    indexer: VectorIndexer,
) -> None:
    owner = _user(pg_session)
    note = _note(pg_session, owner, "We saw the Colosseum.")

    outcome = indexer.index_note(pg_session, note.id)

    assert outcome == IndexOutcome.EMBEDDED
    rows = _rows(pg_session, note.id)
    assert len(rows) == 1
    row = rows[0]
    assert row["notebook_id"] == note.notebook_id
    assert row["chunk_index"] == 0
    assert row["content"].endswith("We saw the Colosseum.")
    assert row["content"].startswith("Title: Rome\nNotebook: Travel")
    assert len(row["embedding"]) == EMBEDDING_DIMENSIONS
    assert row["langchain_metadata"]["title"] == "Rome"
    assert row["langchain_metadata"]["index_version"] == VECTOR_INDEX_VERSION


def test_records_the_note_as_indexed(pg_session: Session, indexer: VectorIndexer) -> None:
    note = _note(pg_session, _user(pg_session), "text")

    indexer.index_note(pg_session, note.id)

    entry = pg_session.get(NoteVectorIndex, note.id)
    assert entry is not None
    assert entry.index_version == VECTOR_INDEX_VERSION
    assert entry.content_hash
    assert note.id not in set(pg_session.scalars(stale_note_ids()))


def test_unchanged_note_is_not_embedded_again(
    pg_session: Session,
    indexer: VectorIndexer,
    embeddings: CountingEmbeddings,
) -> None:
    note = _note(pg_session, _user(pg_session), "text")
    indexer.index_note(pg_session, note.id)
    first = _rows(pg_session, note.id)
    embeddings.calls = 0

    outcome = indexer.index_note(pg_session, note.id)

    assert outcome == IndexOutcome.UNCHANGED
    assert embeddings.calls == 0
    assert [r["langchain_id"] for r in _rows(pg_session, note.id)] == [
        r["langchain_id"] for r in first
    ]


def test_changed_note_replaces_its_chunks(
    pg_session: Session,
    indexer: VectorIndexer,
) -> None:
    owner = _user(pg_session)
    note = _note(pg_session, owner, "first")
    indexer.index_note(pg_session, note.id)
    add_markdown_node(pg_session, note.id, owner, "# Later\n\nsecond", "heading")

    outcome = indexer.index_note(pg_session, note.id)

    assert outcome == IndexOutcome.EMBEDDED
    contents = [row["content"] for row in _rows(pg_session, note.id)]
    assert len(contents) == 2
    assert contents[0].endswith("first")
    assert "Section: Later" in contents[1]


def test_notebook_rename_reembeds_with_the_new_name(
    pg_session: Session,
    indexer: VectorIndexer,
) -> None:
    owner = _user(pg_session)
    note = _note(pg_session, owner, "text")
    indexer.index_note(pg_session, note.id)

    update_notebook(pg_session, note.notebook_id, owner, name=f"Trips {uuid.uuid4()}")
    assert note.id in set(pg_session.scalars(stale_note_ids()))
    outcome = indexer.index_note(pg_session, note.id)

    assert outcome == IndexOutcome.EMBEDDED
    assert "Notebook: Trips" in _rows(pg_session, note.id)[0]["content"]


def test_model_change_reembeds(
    pg_session: Session,
    embeddings: CountingEmbeddings,
) -> None:
    note = _note(pg_session, _user(pg_session), "text")
    VectorIndexer(embeddings, "model-a").index_note(pg_session, note.id)

    outcome = VectorIndexer(embeddings, "model-b").index_note(pg_session, note.id)

    assert outcome == IndexOutcome.EMBEDDED


def test_missing_note(pg_session: Session, indexer: VectorIndexer) -> None:
    assert indexer.index_note(pg_session, uuid.uuid4()) == IndexOutcome.MISSING


def test_wrong_dimension_writes_nothing(pg_session: Session) -> None:
    note = _note(pg_session, _user(pg_session), "text")
    indexer = VectorIndexer(DeterministicFakeEmbedding(size=8), "small")

    with pytest.raises(EmbeddingDimensionError):
        indexer.index_note(pg_session, note.id)

    assert _rows(pg_session, note.id) == []
    assert pg_session.get(NoteVectorIndex, note.id) is None


def test_deleting_a_note_deletes_its_chunks(
    pg_session: Session,
    indexer: VectorIndexer,
) -> None:
    owner = _user(pg_session)
    note = _note(pg_session, owner, "text")
    note_id = note.id
    indexer.index_note(pg_session, note_id)

    delete_note(pg_session, note_id, owner)
    pg_session.expire_all()

    count = pg_session.scalar(
        select(func.count())
        .select_from(note_chunk_embedding)
        .where(note_chunk_embedding.c.note_id == note_id),
    )
    assert count == 0
    assert pg_session.get(NoteVectorIndex, note_id) is None


# --- Configuration ---


def test_no_indexer_without_api_key() -> None:
    assert create_vector_indexer() is None


def test_indexer_uses_the_configured_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("AI_EMBEDDING_MODEL", "text-embedding-3-large")

    with patch("langchain_openai.OpenAIEmbeddings") as openai_embeddings:
        indexer = create_vector_indexer()

    assert indexer is not None
    assert indexer.model == "text-embedding-3-large"
    openai_embeddings.assert_called_once_with(model="text-embedding-3-large")
