"""add blogs

Adds the blog sources of each user and the posts collected from them (see
docs/architecture/blogs.md):

- `blog_directories`: a user's single-level folders of sources.
- `blog_sources`: what to collect and the state of the last collection. The
  uniqueness of a feed per user only holds for sources not archived, so an
  archived feed can be registered again.
- `blog_posts`: metadata and analysis. The text is in the documents directory
  (docs/adr/0004-blog-post-text-in-documents.md).

Revision ID: 2e7a5c9d4f18
Revises: 9b3e6d2f1c47
Create Date: 2026-10-31 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2e7a5c9d4f18"
down_revision: str | Sequence[str] | None = "9b3e6d2f1c47"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "blog_directories",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["assistant.users.uid"],
            name=op.f("fk_blog_directories_owner_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_blog_directories")),
        sa.UniqueConstraint("owner_id", "name", name="uq_blog_directory_owner_name"),
        schema="assistant",
    )
    op.create_table(
        "blog_sources",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("directory_id", sa.UUID(), nullable=True),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("feed_url", sa.String(length=2048), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("preferences", sa.Text(), nullable=True),
        sa.Column("collect_since", sa.DateTime(timezone=True), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("etag", sa.String(length=1024), nullable=True),
        sa.Column("last_modified", sa.String(length=255), nullable=True),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["directory_id"],
            ["assistant.blog_directories.id"],
            name=op.f("fk_blog_sources_directory_id_blog_directories"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["assistant.users.uid"],
            name=op.f("fk_blog_sources_owner_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_blog_sources")),
        schema="assistant",
    )
    op.create_index(
        "uq_blog_source_owner_feed_url",
        "blog_sources",
        ["owner_id", "feed_url"],
        unique=True,
        schema="assistant",
        postgresql_where=sa.text("archived_at IS NULL"),
    )
    op.create_table(
        "blog_posts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("post_key", sa.String(length=64), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("title", sa.String(length=1024), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("match_level", sa.String(length=20), nullable=True),
        sa.Column("motivation", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("embed_status", sa.String(length=20), nullable=False),
        sa.Column("embed_attempts", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["assistant.blog_sources.id"],
            name=op.f("fk_blog_posts_source_id_blog_sources"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_blog_posts")),
        sa.UniqueConstraint("source_id", "post_key", name="uq_blog_post_source_key"),
        schema="assistant",
    )
    op.create_index(
        "ix_blog_posts_source_state_published",
        "blog_posts",
        ["source_id", "state", "published_at"],
        unique=False,
        schema="assistant",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_blog_posts_source_state_published",
        table_name="blog_posts",
        schema="assistant",
    )
    op.drop_table("blog_posts", schema="assistant")
    op.drop_index(
        "uq_blog_source_owner_feed_url",
        table_name="blog_sources",
        schema="assistant",
        postgresql_where=sa.text("archived_at IS NULL"),
    )
    op.drop_table("blog_sources", schema="assistant")
    op.drop_table("blog_directories", schema="assistant")
