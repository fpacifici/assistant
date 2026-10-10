"""widen node position to 2048

Fractional-index positions grow by one character every time a node is
inserted between two neighbours that are already adjacent, so 255 runs out
on heavily edited notes. Widening a VARCHAR is a catalog-only change in
Postgres: no table rewrite, and `ix_nodes_note_id_position` stays valid.
Positions use a 62-character ASCII alphabet, so 2048 characters stay well
under the btree index entry limit (~2700 bytes).

Revision ID: 015c399782be
Revises: a3c91e7d5b20
Create Date: 2026-10-09 22:36:50.739027

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "015c399782be"
down_revision: str | Sequence[str] | None = "a3c91e7d5b20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "nodes",
        "position",
        existing_type=sa.String(length=255),
        type_=sa.String(length=2048),
        existing_nullable=False,
        schema="assistant",
    )


def downgrade() -> None:
    """Downgrade schema.

    Fails if any position is already longer than 255 characters.
    """
    op.alter_column(
        "nodes",
        "position",
        existing_type=sa.String(length=2048),
        type_=sa.String(length=255),
        existing_nullable=False,
        schema="assistant",
    )
