"""drop external documents

Removes the tables of the old Evernote external-adapter pipeline
(`external_sources`, `documents`, `document_metadata`). Notes are imported
into the notes system directly now (see `assistant.adapters.zip_import`).
The data is not recoverable: the downgrade only recreates empty tables.

Revision ID: 7d2e4c1a9b60
Revises: 13fee0c1ad4b
Create Date: 2026-10-14 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7d2e4c1a9b60"
down_revision: str | Sequence[str] | None = "13fee0c1ad4b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_table("document_metadata", schema="assistant")
    op.drop_table("documents", schema="assistant")
    op.drop_table("external_sources", schema="assistant")


def downgrade() -> None:
    """Downgrade schema."""
    op.create_table(
        "external_sources",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("provider_query", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_external_sources")),
        schema="assistant",
    )
    op.create_table(
        "documents",
        sa.Column("uuid", sa.UUID(), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("creation_datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_update_datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("format", sa.String(length=20), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["assistant.external_sources.id"],
            name=op.f("fk_documents_source_id_external_sources"),
        ),
        sa.PrimaryKeyConstraint("uuid", name=op.f("pk_documents")),
        schema="assistant",
    )
    op.create_table(
        "document_metadata",
        sa.Column("document_uuid", sa.UUID(), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_uuid"],
            ["assistant.documents.uuid"],
            name=op.f("fk_document_metadata_document_uuid_documents"),
        ),
        sa.PrimaryKeyConstraint(
            "document_uuid", "key", name=op.f("pk_document_metadata")
        ),
        schema="assistant",
    )
