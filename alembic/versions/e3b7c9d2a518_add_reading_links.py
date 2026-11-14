"""add reading links

`reading_links`: links a user saved to read later, with what the analysis
derived from them (type, title, category, summary) and the user's decision.
The content of a link is never stored.

Revision ID: e3b7c9d2a518
Revises: d8a2f5c1e047
Create Date: 2026-11-14 13:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e3b7c9d2a518"
down_revision: str | Sequence[str] | None = "d8a2f5c1e047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "reading_links",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("url_key", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=1024), nullable=True),
        sa.Column("title_edited", sa.Boolean(), nullable=False),
        sa.Column("link_type", sa.String(length=20), nullable=True),
        sa.Column("category_id", sa.UUID(), nullable=True),
        sa.Column("category_set_by_user", sa.Boolean(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("user_notes", sa.Text(), nullable=True),
        sa.Column("analysis_status", sa.String(length=20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("note_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["assistant.users.uid"],
            name=op.f("fk_reading_links_owner_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["assistant.categories.id"],
            name=op.f("fk_reading_links_category_id_categories"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["note_id"],
            ["assistant.notes.id"],
            name=op.f("fk_reading_links_note_id_notes"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reading_links")),
        sa.UniqueConstraint("owner_id", "url_key", name="uq_reading_link_owner_url_key"),
        schema="assistant",
    )
    op.create_index(
        "ix_reading_links_owner_state_category_created",
        "reading_links",
        ["owner_id", "state", "category_id", "created_at"],
        unique=False,
        schema="assistant",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_reading_links_owner_state_category_created",
        table_name="reading_links",
        schema="assistant",
    )
    op.drop_table("reading_links", schema="assistant")
