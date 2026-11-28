"""add user avatar color

`users.avatar_color`: the user's preferred avatar colour on shared notes, a
name from `assistant.notes.avatar_colors.AVATAR_COLORS`. Null picks a
colour from the user id.

Revision ID: b6d2e8f4a913
Revises: f5a1c7e9b342
Create Date: 2026-11-28 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b6d2e8f4a913"
down_revision: str | Sequence[str] | None = "f5a1c7e9b342"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column("avatar_color", sa.String(length=20), nullable=True),
        schema="assistant",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "avatar_color", schema="assistant")
