"""add chat threads

Adds `chat_threads`, the per-user list of Ask AI conversations (their
messages are langgraph checkpoints keyed by the thread id).

Also drops the vector store of the removed Evernote pipeline: langchain's
legacy `PGVector` tables in the `public` schema, which nothing reads any
more (notes are embedded into `assistant.note_chunk_embedding`, see the
add_vector_index migration). They may not exist, hence IF EXISTS; the
downgrade does not recreate them. The langgraph checkpoint tables in
`public` are kept.

Revision ID: 9b3e6d2f1c47
Revises: c4f1a8e2d930
Create Date: 2026-10-14 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9b3e6d2f1c47"
down_revision: str | Sequence[str] | None = "c4f1a8e2d930"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "chat_threads",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["assistant.users.uid"],
            name=op.f("fk_chat_threads_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_threads")),
        schema="assistant",
    )
    op.create_index(
        "ix_chat_threads_user_id_updated_at",
        "chat_threads",
        ["user_id", "updated_at"],
        unique=False,
        schema="assistant",
    )
    op.execute("DROP TABLE IF EXISTS public.langchain_pg_embedding")
    op.execute("DROP TABLE IF EXISTS public.langchain_pg_collection")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_chat_threads_user_id_updated_at",
        table_name="chat_threads",
        schema="assistant",
    )
    op.drop_table("chat_threads", schema="assistant")
