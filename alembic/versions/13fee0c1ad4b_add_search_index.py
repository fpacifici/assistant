"""add search index

Adds the keyword search index (see docs/adr/0002-postgres-fts-search.md) in
its own tables, apart from notes and nodes: `note_search_index` (one row per
note) and `node_search_index` (one row per block), each deleted with what it
indexes. The plain-text columns are mapped in the ORM; the `search_vector`
tsvector columns and their GIN indexes are Postgres-only, generated from
them, and deliberately not mapped (SQLite tests can't represent them).

After upgrading, run `make reindex-search` to fill the index for existing
notes.

Revision ID: 13fee0c1ad4b
Revises: 015c399782be
Create Date: 2026-10-06 22:43:33.992605

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "13fee0c1ad4b"
down_revision: str | Sequence[str] | None = "015c399782be"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "note_search_index",
        sa.Column("note_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("index_version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["note_id"],
            ["assistant.notes.id"],
            name=op.f("fk_note_search_index_note_id_notes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("note_id", name=op.f("pk_note_search_index")),
        schema="assistant",
    )
    op.create_table(
        "node_search_index",
        sa.Column("node_id", sa.UUID(), nullable=False),
        sa.Column("note_id", sa.UUID(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["node_id"],
            ["assistant.nodes.id"],
            name=op.f("fk_node_search_index_node_id_nodes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["note_id"],
            ["assistant.notes.id"],
            name=op.f("fk_node_search_index_note_id_notes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("node_id", name=op.f("pk_node_search_index")),
        schema="assistant",
    )
    op.create_index(
        "ix_node_search_index_note_id",
        "node_search_index",
        ["note_id"],
        unique=False,
        schema="assistant",
    )
    op.execute(
        "ALTER TABLE assistant.note_search_index ADD COLUMN search_vector tsvector "
        "GENERATED ALWAYS AS ("
        "setweight(to_tsvector('simple'::regconfig, title), 'A') || "
        "setweight(to_tsvector('simple'::regconfig, body), 'B')"
        ") STORED",
    )
    op.execute(
        "CREATE INDEX ix_note_search_index_vector "
        "ON assistant.note_search_index USING gin (search_vector)",
    )
    op.execute(
        "ALTER TABLE assistant.node_search_index ADD COLUMN search_vector tsvector "
        "GENERATED ALWAYS AS (to_tsvector('simple'::regconfig, text)) STORED",
    )
    op.execute(
        "CREATE INDEX ix_node_search_index_vector "
        "ON assistant.node_search_index USING gin (search_vector)",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_node_search_index_note_id",
        table_name="node_search_index",
        schema="assistant",
    )
    op.drop_table("node_search_index", schema="assistant")
    op.drop_table("note_search_index", schema="assistant")
