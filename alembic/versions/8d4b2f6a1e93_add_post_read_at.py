"""add post read_at

`blog_posts.read_at`: when the user marked the post read. Null means it is
still to read. It is independent of the verdict in `state`.

Revision ID: 8d4b2f6a1e93
Revises: 6c1d8e3b7a24
Create Date: 2026-11-06 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8d4b2f6a1e93"
down_revision: str | Sequence[str] | None = "6c1d8e3b7a24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "blog_posts",
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        schema="assistant",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("blog_posts", "read_at", schema="assistant")
