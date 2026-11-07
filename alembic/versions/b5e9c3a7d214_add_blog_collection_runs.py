"""add blog collection runs

- `blog_collection_runs`: one row per source each time the job or a manual
  refresh collects it, with how reading the source went.
- `blog_collection_entries`: what the source listed in a run and what became
  of each entry, with a copy of the model's answer.

Revision ID: b5e9c3a7d214
Revises: 8d4b2f6a1e93
Create Date: 2026-11-07 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b5e9c3a7d214"
down_revision: str | Sequence[str] | None = "8d4b2f6a1e93"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "blog_collection_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("trigger", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(length=20), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("interrupted", sa.Boolean(), nullable=False),
        sa.Column("entries_found", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["assistant.blog_sources.id"],
            name=op.f("fk_blog_collection_runs_source_id_blog_sources"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_blog_collection_runs")),
        schema="assistant",
    )
    op.create_index(
        "ix_blog_collection_runs_source_started",
        "blog_collection_runs",
        ["source_id", "started_at"],
        unique=False,
        schema="assistant",
    )
    op.create_table(
        "blog_collection_entries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("title", sa.String(length=1024), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verdict", sa.String(length=20), nullable=False),
        sa.Column("post_id", sa.UUID(), nullable=True),
        sa.Column("feed_text_chars", sa.Integer(), nullable=True),
        sa.Column("analysis", sa.String(length=20), nullable=True),
        sa.Column("text_source", sa.String(length=20), nullable=True),
        sa.Column("text_chars", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("match_level", sa.String(length=20), nullable=True),
        sa.Column("motivation", sa.Text(), nullable=True),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["post_id"],
            ["assistant.blog_posts.id"],
            name=op.f("fk_blog_collection_entries_post_id_blog_posts"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["assistant.blog_collection_runs.id"],
            name=op.f("fk_blog_collection_entries_run_id_blog_collection_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_blog_collection_entries")),
        schema="assistant",
    )
    op.create_index(
        "ix_blog_collection_entries_run_position",
        "blog_collection_entries",
        ["run_id", "position"],
        unique=False,
        schema="assistant",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_blog_collection_entries_run_position",
        table_name="blog_collection_entries",
        schema="assistant",
    )
    op.drop_table("blog_collection_entries", schema="assistant")
    op.drop_index(
        "ix_blog_collection_runs_source_started",
        table_name="blog_collection_runs",
        schema="assistant",
    )
    op.drop_table("blog_collection_runs", schema="assistant")
