"""SQLAlchemy database models."""

from __future__ import annotations

import uuid as uuid_module
from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
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


class FileState(str, Enum):
    """Upload state for a File."""

    PENDING = "pending"
    UPLOADING = "uploading"
    COMPLETE = "complete"
    EXPIRED = "expired"


class MarkdownBlockType(str, Enum):
    """Markdown block type enumeration."""

    PARAGRAPH = "paragraph"
    HEADING = "heading"
    BLOCKQUOTE = "blockquote"
    LIST_ITEM = "list_item"
    IMAGE = "image"
    CODE_BLOCK = "code_block"


class SubjectType(str, Enum):
    """The kind of subject an Entitlement grants access to."""

    NOTE = "note"
    NOTEBOOK = "notebook"


class PermissionName(str, Enum):
    """A single grantable action on a Note or Notebook."""

    VIEW_NOTE = "view_note"
    UPDATE = "update"
    DELETE_NOTE = "delete_note"
    SHARE_NOTE = "share_note"
    VIEW_NOTEBOOK = "view_notebook"
    UPDATE_NOTEBOOK = "update_notebook"
    DELETE_NOTEBOOK = "delete_notebook"
    CREATE_NOTES = "create_notes"
    LIST_NOTES = "list_notes"
    OWN_NOTES = "own_notes"
    DELETE_NOTES = "delete_notes"
    VIEW_NOTES = "view_notes"
    SHARE_NOTEBOOK = "share_notebook"


class RoleName(str, Enum):
    """A fixed, named bundle of permissions grantable on a subject."""

    NOTEBOOK_OWNER = "notebook_owner"
    NOTEBOOK_VIEWER = "notebook_viewer"
    NOTEBOOK_EDITOR = "notebook_editor"
    NOTE_OWNER = "note_owner"
    NOTE_VIEWER = "note_viewer"
    NOTE_EDITOR = "note_editor"


class InviteState(str, Enum):
    """Lifecycle state of an account Invite. Only PENDING transitions."""

    PENDING = "pending"
    VOID = "void"
    CONVERTED = "converted"


class UserStatus(str, Enum):
    """Account activation state."""

    PENDING = "pending"
    ACTIVE = "active"


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
    invite_quota_remaining: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=UserStatus.ACTIVE.value
    )

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
    credentials: Mapped[list[Credential]] = relationship(
        "Credential",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    entitlements: Mapped[list[Entitlement]] = relationship(
        "Entitlement",
        back_populates="principal",
        cascade="all, delete-orphan",
    )
    invites_sent: Mapped[list[Invite]] = relationship(
        "Invite",
        back_populates="inviter",
        cascade="all, delete-orphan",
    )
    email_confirmation: Mapped[EmailConfirmation | None] = relationship(
        "EmailConfirmation",
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )


class Credential(Base):
    """User credential — one row per authentication provider per user."""

    __tablename__ = "credentials"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_credential_user_provider"),
        UniqueConstraint(
            "provider",
            "provider_subject",
            name="uq_credential_provider_subject",
        ),
        {"schema": "assistant"},
    )

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid_module.uuid4,
    )
    user_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant.users.uid"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    credential_hash: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    provider_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)

    user: Mapped[User] = relationship("User", back_populates="credentials")


class RefreshToken(Base):
    """Refresh token with family tracking for rotation and replay detection."""

    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("ix_refresh_tokens_token_hash", "token_hash", unique=True),
        {"schema": "assistant"},
    )

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid_module.uuid4,
    )
    user_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant.users.uid"),
        nullable=False,
    )
    family_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    user: Mapped[User] = relationship("User", back_populates="refresh_tokens")


class Invite(Base):
    """A pending account invite for an email with no matching User yet.

    `state` is unconstrained at the DB level, validated only in the service
    layer — same precedent as `Node.node_type`/`Entitlement.role_name`.
    No `invitee_email` uniqueness — multiple pending invites (from the same
    or different senders) to the same address are allowed.
    """

    __tablename__ = "invites"
    __table_args__ = {"schema": "assistant"}  # noqa: RUF012

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid_module.uuid4,
    )
    invitee_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    inviter_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant.users.uid"),
        nullable=False,
    )
    state: Mapped[str] = mapped_column(
        String(20), nullable=False, default=InviteState.PENDING.value
    )
    quota_consumed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    inviter: Mapped[User] = relationship("User", back_populates="invites_sent")


class EmailConfirmation(Base):
    """The single pending email-confirmation token for a not-yet-active User.

    One row per user — user_id IS the primary key. A resend overwrites this
    same row's token/expiry/count rather than creating a new one: exactly
    one confirmation cycle is meaningful per pending registration. Deleted
    via cascade when the User is deleted, including the lazy reap of an
    expired, still-unconfirmed registration (see
    auth.service._reap_expired_pending_registration) — no separate cleanup
    path needed.
    """

    __tablename__ = "email_confirmations"
    __table_args__ = {"schema": "assistant"}  # noqa: RUF012

    user_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant.users.uid"),
        primary_key=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    resend_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    user: Mapped[User] = relationship("User", back_populates="email_confirmation")


class Notebook(Base):
    """Notebook model."""

    __tablename__ = "notebooks"
    __table_args__ = (
        UniqueConstraint("name", name="uq_notebook_name"),
        {"schema": "assistant"},
    )

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
    entitlements: Mapped[list[Entitlement]] = relationship(
        "Entitlement",
        back_populates="notebook",
        cascade="all, delete-orphan",
    )


class Note(Base):
    """Note model."""

    __tablename__ = "notes"
    __table_args__ = (
        UniqueConstraint(
            "notebook_id",
            "external_id",
            name="uq_note_notebook_external_id",
        ),
        {"schema": "assistant"},
    )

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
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
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
    files: Mapped[list[File]] = relationship(
        "File",
        back_populates="note",
        cascade="all, delete-orphan",
    )
    entitlements: Mapped[list[Entitlement]] = relationship(
        "Entitlement",
        back_populates="note",
        cascade="all, delete-orphan",
    )


class File(Base):
    """Upload file metadata — tracks chunked upload lifecycle."""

    __tablename__ = "files"
    __table_args__ = {"schema": "assistant"}  # noqa: RUF012

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
    file_name: Mapped[str] = mapped_column(String(1024), nullable=False)
    creation_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    state: Mapped[str] = mapped_column(
        String(20), nullable=False, default=FileState.PENDING.value
    )

    note: Mapped[Note] = relationship("Note", back_populates="files")
    chunks: Mapped[list[Chunk]] = relationship(
        "Chunk",
        back_populates="file",
        cascade="all, delete-orphan",
        order_by="Chunk.part_number",
    )


class Chunk(Base):
    """One part of a chunked upload, stored as a file on disk."""

    __tablename__ = "chunks"
    __table_args__ = {"schema": "assistant"}  # noqa: RUF012

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid_module.uuid4,
    )
    file_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant.files.id"),
        nullable=False,
    )
    part_number: Mapped[int] = mapped_column(Integer, nullable=False)
    file_name: Mapped[str] = mapped_column(String(1024), nullable=False)
    creation_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    file: Mapped[File] = relationship("File", back_populates="chunks")


class Node(Base):
    """Node model representing a content chunk within a note."""

    __tablename__ = "nodes"
    __table_args__ = (
        CheckConstraint(
            "(node_type = 'text' AND payload IS NOT NULL"
            " AND attachment_id IS NULL AND block_type IS NULL)"
            " OR "
            "(node_type = 'attachment' AND payload IS NOT NULL"
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
        ForeignKey("assistant.files.id"),
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
    attachment: Mapped[File | None] = relationship("File")


class Entitlement(Base):
    """A grant of a permission or role to a principal on a Note or Notebook.

    Exactly one of (note_id, notebook_id) and exactly one of
    (permission_name, role_name) must be set. `permission_name`/`role_name`
    are unconstrained plain strings at the DB level — validated against the
    `PermissionName`/`RoleName` enums in the service layer, the same pattern
    used for `Node.node_type`/`Node.block_type`.
    """

    __tablename__ = "entitlements"
    __table_args__ = (
        CheckConstraint(
            "(note_id IS NOT NULL AND notebook_id IS NULL)"
            " OR (note_id IS NULL AND notebook_id IS NOT NULL)",
            name="ck_entitlement_one_subject",
        ),
        CheckConstraint(
            "(permission_name IS NOT NULL AND role_name IS NULL)"
            " OR (permission_name IS NULL AND role_name IS NOT NULL)",
            name="ck_entitlement_one_grant",
        ),
        UniqueConstraint(
            "principal_id",
            "note_id",
            "notebook_id",
            "permission_name",
            "role_name",
            name="uq_entitlement_no_duplicate_grant",
        ),
        {"schema": "assistant"},
    )

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid_module.uuid4,
    )
    principal_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant.users.uid"),
        nullable=False,
    )
    note_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant.notes.id"),
        nullable=True,
    )
    notebook_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant.notebooks.id"),
        nullable=True,
    )
    permission_name: Mapped[str | None] = mapped_column(String(30), nullable=True)
    role_name: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    principal: Mapped[User] = relationship("User", back_populates="entitlements")
    note: Mapped[Note | None] = relationship("Note", back_populates="entitlements")
    notebook: Mapped[Notebook | None] = relationship(
        "Notebook",
        back_populates="entitlements",
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
