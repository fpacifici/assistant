"""add notebook activity

`notebook_activity`: when each user last changed a note in each notebook,
so the sidebar can list notebooks by the caller's own recent edits.

Existing rows are backfilled from what the data already records: the
latest node a user authored in the notebook, or the latest note they
created there.

Revision ID: f5a1c7e9b342
Revises: 4a7f2c9e1b58
Create Date: 2026-11-27 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f5a1c7e9b342"
down_revision: str | Sequence[str] | None = "4a7f2c9e1b58"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "notebook_activity",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("notebook_id", sa.UUID(), nullable=False),
        sa.Column("last_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["assistant.users.uid"],
            name=op.f("fk_notebook_activity_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["notebook_id"],
            ["assistant.notebooks.id"],
            name=op.f("fk_notebook_activity_notebook_id_notebooks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "user_id", "notebook_id", name=op.f("pk_notebook_activity")
        ),
        schema="assistant",
    )
    op.execute(
        """
        INSERT INTO assistant.notebook_activity (user_id, notebook_id, last_updated_at)
        SELECT user_id, notebook_id, max(ts)
        FROM (
            SELECT nodes.author_id AS user_id, notes.notebook_id, nodes.update_timestamp AS ts
            FROM assistant.nodes JOIN assistant.notes ON notes.id = nodes.note_id
            UNION ALL
            SELECT notes.owner_id, notes.notebook_id, notes.creation_timestamp
            FROM assistant.notes
        ) AS edits
        GROUP BY user_id, notebook_id
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("notebook_activity", schema="assistant")
