"""add vector index

Adds the note embeddings for semantic search (see
docs/adr/0003-pgvector-note-embeddings.md):

- `note_vector_index`: one row per note tracking whether its embeddings are
  up to date (ORM-mapped).
- `note_chunk_embedding`: one row per chunk of a note, with its pgvector
  embedding. Postgres-only and deliberately not mapped in the ORM (SQLite
  tests can't represent `vector`); its layout is the one langchain's
  `PGVectorStore` expects (`langchain_id`, `content`, `embedding`,
  `langchain_metadata`), plus `note_id`/`notebook_id`/`chunk_index` columns
  used to filter by permission and to replace a note's chunks.

After upgrading, run `make reindex-vectors` to embed existing notes.

Revision ID: c4f1a8e2d930
Revises: 7d2e4c1a9b60
Create Date: 2026-10-14 11:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4f1a8e2d930"
down_revision: str | Sequence[str] | None = "7d2e4c1a9b60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "note_vector_index",
        sa.Column("note_id", sa.UUID(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("index_version", sa.Integer(), nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stale_since", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["note_id"],
            ["assistant.notes.id"],
            name=op.f("fk_note_vector_index_note_id_notes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("note_id", name=op.f("pk_note_vector_index")),
        schema="assistant",
    )
    op.execute(
        "CREATE TABLE assistant.note_chunk_embedding ("
        "langchain_id uuid PRIMARY KEY, "
        "content text NOT NULL, "
        "embedding vector(1536) NOT NULL, "
        "note_id uuid NOT NULL "
        "CONSTRAINT fk_note_chunk_embedding_note_id_notes "
        "REFERENCES assistant.notes (id) ON DELETE CASCADE, "
        "notebook_id uuid NOT NULL, "
        "chunk_index integer NOT NULL, "
        "langchain_metadata jsonb NOT NULL DEFAULT '{}'::jsonb"
        ")",
    )
    op.execute(
        "CREATE INDEX ix_note_chunk_embedding_note_id "
        "ON assistant.note_chunk_embedding (note_id)",
    )
    op.execute(
        "CREATE INDEX ix_note_chunk_embedding_notebook_id "
        "ON assistant.note_chunk_embedding (notebook_id)",
    )
    op.execute(
        "CREATE INDEX ix_note_chunk_embedding_embedding "
        "ON assistant.note_chunk_embedding "
        "USING hnsw (embedding vector_cosine_ops)",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE assistant.note_chunk_embedding")
    op.drop_table("note_vector_index", schema="assistant")
