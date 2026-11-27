"""add note presence

`note_presence`: the browser tabs that have a note open, with their cursor
and when they last beat. Rows older than the presence TTL are inactive.

Revision ID: 4a7f2c9e1b58
Revises: e3b7c9d2a518
Create Date: 2026-11-27 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4a7f2c9e1b58"
down_revision: str | Sequence[str] | None = "e3b7c9d2a518"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "note_presence",
        sa.Column("note_id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("cursor_node_id", sa.UUID(), nullable=True),
        sa.Column("cursor_offset", sa.Integer(), nullable=True),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["note_id"],
            ["assistant.notes.id"],
            name=op.f("fk_note_presence_note_id_notes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["assistant.users.uid"],
            name=op.f("fk_note_presence_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("note_id", "client_id", name=op.f("pk_note_presence")),
        schema="assistant",
    )
    op.create_index(
        "ix_note_presence_last_seen",
        "note_presence",
        ["last_seen"],
        unique=False,
        schema="assistant",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_note_presence_last_seen", table_name="note_presence", schema="assistant"
    )
    op.drop_table("note_presence", schema="assistant")
