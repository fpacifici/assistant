"""add search index

Adds the keyword search index (see docs/adr/0002-postgres-fts-search.md).
The plain-text columns are mapped in the ORM; the `search_vector` tsvector
columns and their GIN indexes are Postgres-only, generated from them, and
deliberately not mapped (SQLite tests can't represent them).

After upgrading, run `python -m assistant.cli.reindex_search` to fill the
index for existing notes.

Revision ID: 13fee0c1ad4b
Revises: a3c91e7d5b20
Create Date: 2026-10-06 22:43:33.992605

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "13fee0c1ad4b"
down_revision: str | Sequence[str] | None = "a3c91e7d5b20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "nodes",
        sa.Column("search_text", sa.Text(), server_default="", nullable=False),
        schema="assistant",
    )
    op.add_column(
        "notes",
        sa.Column("search_title", sa.Text(), server_default="", nullable=False),
        schema="assistant",
    )
    op.add_column(
        "notes",
        sa.Column("search_body", sa.Text(), server_default="", nullable=False),
        schema="assistant",
    )
    op.add_column(
        "notes",
        sa.Column(
            "search_index_version", sa.Integer(), server_default="0", nullable=False
        ),
        schema="assistant",
    )
    op.execute(
        "ALTER TABLE assistant.nodes ADD COLUMN search_vector tsvector "
        "GENERATED ALWAYS AS (to_tsvector('simple'::regconfig, search_text)) STORED",
    )
    op.execute(
        "CREATE INDEX ix_nodes_search_vector ON assistant.nodes USING gin (search_vector)",
    )
    op.execute(
        "ALTER TABLE assistant.notes ADD COLUMN search_vector tsvector "
        "GENERATED ALWAYS AS ("
        "setweight(to_tsvector('simple'::regconfig, search_title), 'A') || "
        "setweight(to_tsvector('simple'::regconfig, search_body), 'B')"
        ") STORED",
    )
    op.execute(
        "CREATE INDEX ix_notes_search_vector ON assistant.notes USING gin (search_vector)",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS assistant.ix_notes_search_vector")
    op.execute("ALTER TABLE assistant.notes DROP COLUMN IF EXISTS search_vector")
    op.execute("DROP INDEX IF EXISTS assistant.ix_nodes_search_vector")
    op.execute("ALTER TABLE assistant.nodes DROP COLUMN IF EXISTS search_vector")
    op.drop_column("notes", "search_index_version", schema="assistant")
    op.drop_column("notes", "search_body", schema="assistant")
    op.drop_column("notes", "search_title", schema="assistant")
    op.drop_column("nodes", "search_text", schema="assistant")
