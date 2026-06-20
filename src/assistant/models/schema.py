"""SQLAlchemy database models."""

from __future__ import annotations

import uuid as uuid_module
from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from assistant.models.database import Base


class DocumentFormat(str, Enum):
    """Document format enumeration."""

    TEXT = "text"
    MARKDOWN = "markdown"
    PDF = "pdf"


class NodeType(str, Enum):
    """Node type enumeration."""

    TEXT = "text"
    ATTACHMENT = "attachment"
    MARKDOWN = "markdown"


class MarkdownBlockType(str, Enum):
    """Markdown block type enumeration."""

    PARAGRAPH = "paragraph"
    HEADING = "heading"
    BLOCKQUOTE = "blockquote"
    LIST_ITEM = "list_item"
    IMAGE = "image"
    CODE_BLOCK = "code_block"


class User(Base):
    """User model."""

    __tablename__ = "users"
    __table_args__ = {"schema": "assistant"}  # noqa: RUF012

    uid: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid_module.uuid4,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
    )
    firstname: Mapped[str] = mapped_column(String(255), nullable=False)
    lastname: Mapped[str] = mapped_column(String(255), nullable=False)

    notebooks: Mapped[list[Notebook]] = relationship(
        "Notebook",
        back_populates="owner",
        cascade="all, delete-orphan",
    )
    notes: Mapped[list[Note]] = relationship(
        "Note",
        back_populates="owner",
        cascade="all, delete-orphan",
    )


class Notebook(Base):
    """Notebook model."""

    __tablename__ = "notebooks"
    __table_args__ = {"schema": "assistant"}  # noqa: RUF012

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid_module.uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant.users.uid"),
        nullable=False,
    )

    owner: Mapped[User] = relationship(
        "User",
        back_populates="notebooks",
    )
    notes: Mapped[list[Note]] = relationship(
        "Note",
        back_populates="notebook",
        cascade="all, delete-orphan",
    )


class Note(Base):
    """Note model."""

    __tablename__ = "notes"
    __table_args__ = {"schema": "assistant"}  # noqa: RUF012

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid_module.uuid4,
    )
    notebook_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant.notebooks.id"),
        nullable=False,
    )
    owner_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant.users.uid"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    creation_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    update_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    notebook: Mapped[Notebook] = relationship(
        "Notebook",
        back_populates="notes",
    )
    owner: Mapped[User] = relationship(
        "User",
        back_populates="notes",
    )
    nodes: Mapped[list[Node]] = relationship(
        "Node",
        back_populates="note",
        cascade="all, delete-orphan",
        order_by="Node.position",
    )


class AttachmentMetadata(Base):
    """Attachment metadata model."""

    __tablename__ = "attachment_metadata"
    __table_args__ = {"schema": "assistant"}  # noqa: RUF012

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid_module.uuid4,
    )
    path: Mapped[str] = mapped_column(String(1024), nullable=False)


class Node(Base):
    """Node model representing a content chunk within a note."""

    __tablename__ = "nodes"
    __table_args__ = (
        CheckConstraint(
            "(node_type = 'text' AND payload IS NOT NULL"
            " AND attachment_id IS NULL AND block_type IS NULL)"
            " OR "
            "(node_type = 'attachment' AND payload IS NULL"
            " AND attachment_id IS NOT NULL AND block_type IS NULL)"
            " OR "
            "(node_type = 'markdown' AND payload IS NOT NULL"
            " AND attachment_id IS NULL AND block_type IS NOT NULL)",
            name="ck_node_type_fields",
        ),
        Index("ix_nodes_note_id_position", "note_id", "position"),
        {"schema": "assistant"},
    )

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid_module.uuid4,
    )
    note_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant.notes.id"),
        nullable=False,
    )
    position: Mapped[str] = mapped_column(String(255), nullable=False)
    author_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant.users.uid"),
        nullable=False,
    )
    node_type: Mapped[str] = mapped_column(String(20), nullable=False)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    block_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    attachment_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant.attachment_metadata.id"),
        nullable=True,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    update_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    note: Mapped[Note] = relationship(
        "Note",
        back_populates="nodes",
    )
    author: Mapped[User] = relationship("User")
    attachment: Mapped[AttachmentMetadata | None] = relationship(
        "AttachmentMetadata",
    )


class Document(Base):
    """Document model representing a document from an external source.

    Attributes:
        uuid: Primary key UUID generated by the system.
        external_id: ID of the document in the external source.
        creation_datetime: When the document was created in the external source.
        last_update_datetime: When the document was last updated in the external source.
        title: Title of the document from the external source.
        format: Format of the document (text, markdown, or PDF).
        source_id: Foreign key to the ExternalSource.
        source: Relationship to the ExternalSource.
        metadata_entries: Collection of metadata key-value pairs.
    """

    __tablename__ = "documents"
    __table_args__ = {"schema": "assistant"}  # noqa: RUF012

    uuid: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid_module.uuid4,
        nullable=False,
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    creation_datetime: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    last_update_datetime: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    format: Mapped[DocumentFormat] = mapped_column(
        String(20),
        nullable=False,
    )
    source_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant.external_sources.id"),
        nullable=False,
    )

    # Relationships
    source: Mapped[ExternalSource] = relationship(
        "ExternalSource",
        back_populates="documents",
    )
    metadata_entries: Mapped[list[DocumentMetadata]] = relationship(
        "DocumentMetadata",
        back_populates="document",
        cascade="all, delete-orphan",
    )

    def set_metadata(
        self,
        key: str,
        value: str,
    ) -> None:
        """Set or update a metadata entry for this document.

        If a metadata entry with the given key already exists, its value is updated.
        Otherwise, a new metadata row is added for this document.

        Args:
            key: Metadata key to set.
            value: Metadata value to associate with the key.
        """
        for entry in self.metadata_entries:
            if entry.key == key:
                entry.value = value
                return

        self.metadata_entries.append(
            DocumentMetadata(
                document_uuid=self.uuid,
                key=key,
                value=value,
            ),
        )

    @property
    def metadata_dict(self) -> dict[str, str]:
        """Return document metadata as a mapping from key to value.

        Returns:
            A dictionary mapping metadata keys to their corresponding values.
        """
        return {entry.key: entry.value for entry in self.metadata_entries}


class ExternalSource(Base):
    """External source model representing a configured external source.

    Attributes:
        id: Primary key UUID.
        provider: Provider identifier (e.g., "evernote", "fake").
        provider_query: Source-specific query parameters as JSON string.
        documents: Relationship to documents from this source.
    """

    __tablename__ = "external_sources"
    __table_args__ = {"schema": "assistant"}  # noqa: RUF012

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid_module.uuid4,
    )
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_query: Mapped[str] = mapped_column(Text, nullable=True)

    # Relationships
    documents: Mapped[list[Document]] = relationship(
        "Document",
        back_populates="source",
        cascade="all, delete-orphan",
    )


class DocumentMetadata(Base):
    """Document metadata key-value pair.

    Each row represents a single metadata entry associated with a document.

    Attributes:
        document_uuid: UUID of the related document.
        key: Metadata key.
        value: Metadata value.
        document: Relationship to the owning Document.
    """

    __tablename__ = "document_metadata"
    __table_args__ = {"schema": "assistant"}  # noqa: RUF012

    document_uuid: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant.documents.uuid"),
        primary_key=True,
        nullable=False,
    )
    key: Mapped[str] = mapped_column(String(255), primary_key=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationships
    document: Mapped[Document] = relationship(
        "Document",
        back_populates="metadata_entries",
    )
