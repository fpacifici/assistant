"""add post tags and embeddings

- `post_tags`: tags on blog posts, from the same vocabulary as notes.
- `post_chunk_embedding`: one row per chunk of a useful post, with its pgvector
  embedding. Postgres-only and not mapped in the ORM, like
  `note_chunk_embedding`, and kept apart from it so nothing that searches notes
  can reach a post.

Revision ID: 6c1d8e3b7a24
Revises: 2e7a5c9d4f18
Create Date: 2026-10-31 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6c1d8e3b7a24"
down_revision: str | Sequence[str] | None = "2e7a5c9d4f18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "post_tags",
        sa.Column("post_id", sa.UUID(), nullable=False),
        sa.Column("tag_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["post_id"],
            ["assistant.blog_posts.id"],
            name=op.f("fk_post_tags_post_id_blog_posts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"],
            ["assistant.tags.id"],
            name=op.f("fk_post_tags_tag_id_tags"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("post_id", "tag_id", name=op.f("pk_post_tags")),
        schema="assistant",
    )
    op.create_index(
        "ix_post_tags_tag_id",
        "post_tags",
        ["tag_id"],
        unique=False,
        schema="assistant",
    )
    op.execute(
        "CREATE TABLE assistant.post_chunk_embedding ("
        "langchain_id uuid PRIMARY KEY, "
        "content text NOT NULL, "
        "embedding vector(1536) NOT NULL, "
        "post_id uuid NOT NULL "
        "CONSTRAINT fk_post_chunk_embedding_post_id_blog_posts "
        "REFERENCES assistant.blog_posts (id) ON DELETE CASCADE, "
        "source_id uuid NOT NULL, "
        "owner_id uuid NOT NULL, "
        "chunk_index integer NOT NULL, "
        "langchain_metadata jsonb NOT NULL DEFAULT '{}'::jsonb"
        ")",
    )
    op.execute(
        "CREATE INDEX ix_post_chunk_embedding_post_id "
        "ON assistant.post_chunk_embedding (post_id)",
    )
    op.execute(
        "CREATE INDEX ix_post_chunk_embedding_owner_id "
        "ON assistant.post_chunk_embedding (owner_id)",
    )
    op.execute(
        "CREATE INDEX ix_post_chunk_embedding_embedding "
        "ON assistant.post_chunk_embedding "
        "USING hnsw (embedding vector_cosine_ops)",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE assistant.post_chunk_embedding")
    op.drop_index("ix_post_tags_tag_id", table_name="post_tags", schema="assistant")
    op.drop_table("post_tags", schema="assistant")
