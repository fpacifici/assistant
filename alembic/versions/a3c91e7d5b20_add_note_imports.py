"""add note_imports

Revision ID: a3c91e7d5b20
Revises: eb31f745ef86
Create Date: 2026-10-03 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3c91e7d5b20"
down_revision: str | Sequence[str] | None = "eb31f745ef86"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # No backfill: notes imported before this table existed stay untracked,
    # since there is no way to tell whether they were edited after import.
    op.create_table(
        "note_imports",
        sa.Column("note_id", sa.UUID(), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_path", sa.String(length=1024), nullable=False),
        sa.ForeignKeyConstraint(
            ["note_id"],
            ["assistant.notes.id"],
            name=op.f("fk_note_imports_note_id_notes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("note_id", name=op.f("pk_note_imports")),
        schema="assistant",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("note_imports", schema="assistant")
