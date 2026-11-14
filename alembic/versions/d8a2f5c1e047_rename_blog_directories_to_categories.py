"""rename blog directories to categories

Blog directories become categories, shared by blogs and the reading list:

- `blog_directories` is renamed `categories`, with its constraints, and gets a
  nullable `description` that the reading list's model reads.
- `blog_sources.directory_id` is renamed `category_id`.

Existing directories keep their id and name and get no description.

Revision ID: d8a2f5c1e047
Revises: b5e9c3a7d214
Create Date: 2026-11-14 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8a2f5c1e047"
down_revision: str | Sequence[str] | None = "b5e9c3a7d214"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (old name, new name) of every constraint that names a renamed table or column.
_CATEGORY_CONSTRAINTS = (
    ("pk_blog_directories", "pk_categories"),
    ("fk_blog_directories_owner_id_users", "fk_categories_owner_id_users"),
    ("uq_blog_directory_owner_name", "uq_category_owner_name"),
)
_SOURCE_FK = (
    "fk_blog_sources_directory_id_blog_directories",
    "fk_blog_sources_category_id_categories",
)


def _rename_constraint(table: str, old: str, new: str) -> None:
    op.execute(f'ALTER TABLE assistant.{table} RENAME CONSTRAINT "{old}" TO "{new}"')


def upgrade() -> None:
    """Upgrade schema."""
    op.rename_table("blog_directories", "categories", schema="assistant")
    for old, new in _CATEGORY_CONSTRAINTS:
        _rename_constraint("categories", old, new)
    op.add_column(
        "categories",
        sa.Column("description", sa.Text(), nullable=True),
        schema="assistant",
    )
    op.alter_column(
        "blog_sources",
        "directory_id",
        new_column_name="category_id",
        schema="assistant",
    )
    _rename_constraint("blog_sources", *_SOURCE_FK)


def downgrade() -> None:
    """Downgrade schema. Descriptions are lost."""
    _rename_constraint("blog_sources", _SOURCE_FK[1], _SOURCE_FK[0])
    op.alter_column(
        "blog_sources",
        "category_id",
        new_column_name="directory_id",
        schema="assistant",
    )
    op.drop_column("categories", "description", schema="assistant")
    for old, new in _CATEGORY_CONSTRAINTS:
        _rename_constraint("categories", new, old)
    op.rename_table("categories", "blog_directories", schema="assistant")
