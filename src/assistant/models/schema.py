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
    text,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from assistant.models.database import Base


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


class BlogSourceKind(str, Enum):
    """How a blog source is read."""

    FEED = "feed"
    SITEMAP = "sitemap"


class BlogPostStatus(str, Enum):
    """Where a post is in the pipeline.

    `SKIPPED` rows only remember a dateless or too-old sitemap URL so it is
    not fetched again; the API never returns them.
    """

    PENDING = "pending"
    PROCESSED = "processed"
    FAILED = "failed"
    SKIPPED = "skipped"


class BlogPostState(str, Enum):
    """The user's verdict on a post."""

    NEW = "new"
    USEFUL = "useful"
    NOT_USEFUL = "not_useful"


class BlogMatchLevel(str, Enum):
    """How well a post fits its source's preferences."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class BlogEmbedStatus(str, Enum):
    """Whether a post's embeddings exist. Only useful posts have them."""

    NONE = "none"
    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"


class ReadingLinkType(str, Enum):
    """What a reading link points at, decided by the analysis."""

    WEB = "web"
    PDF = "pdf"
    TEXT = "text"
    YOUTUBE = "youtube"
    OTHER = "other"


class ReadingAnalysisStatus(str, Enum):
    """Where a reading link is in the analysis pipeline."""

    PENDING = "pending"
    DONE = "done"
    NOT_SUMMARIZABLE = "not_summarizable"
    FAILED = "failed"


class ReadingLinkState(str, Enum):
    """The user's decision on a reading link."""

    TO_READ = "to_read"
    DISCARDED = "discarded"
    PROMOTED = "promoted"


class BlogRunTrigger(str, Enum):
    """What started a collection run."""

    JOB = "job"
    MANUAL = "manual"


class BlogRunOutcome(str, Enum):
    """How reading the source went. Null on a run still reading it."""

    COLLECTED = "collected"
    NOT_MODIFIED = "not_modified"
    FAILED = "failed"


class BlogEntryVerdict(str, Enum):
    """What the collection made of one entry of a feed or sitemap."""

    NEW = "new"  # stored as a new post
    STORED = "stored"  # collected by an earlier run
    TOO_OLD = "too_old"  # before the source's collection start
    OVER_CAP = "over_cap"  # left for the next run
    NO_DATE = "no_date"  # a sitemap page with no date: never fetched again
    UNREADABLE = "unreadable"  # a sitemap page that could not be read now
    ROBOTS = "robots"  # robots.txt disallows it
    INVALID = "invalid"  # no link, or a link too long to store
    RETRY = "retry"  # collected earlier and analyzed again in this run


class BlogEntryAnalysis(str, Enum):
    """What analyzing an entry's post did in the run."""

    PROCESSED = "processed"
    TOO_SHORT = "too_short"
    ERROR = "error"  # tried again by the next run
    FAILED = "failed"  # out of attempts


class BlogTextSource(str, Enum):
    """Where the text given to the model came from."""

    FILE = "file"  # saved by an earlier attempt
    PAGE = "page"
    FEED = "feed"


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
    tags: Mapped[list[Tag]] = relationship(
        "Tag",
        back_populates="owner",
        cascade="all, delete-orphan",
    )
    chat_threads: Mapped[list[ChatThread]] = relationship(
        "ChatThread",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    categories: Mapped[list[Category]] = relationship(
        "Category",
        back_populates="owner",
        cascade="all, delete-orphan",
    )
    blog_sources: Mapped[list[BlogSource]] = relationship(
        "BlogSource",
        back_populates="owner",
        cascade="all, delete-orphan",
    )
    reading_links: Mapped[list[ReadingLink]] = relationship(
        "ReadingLink",
        back_populates="owner",
        cascade="all, delete-orphan",
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
    import_record: Mapped[NoteImport | None] = relationship(
        "NoteImport",
        back_populates="note",
        cascade="all, delete-orphan",
        uselist=False,
    )
    tag_links: Mapped[list[NoteTag]] = relationship(
        "NoteTag",
        back_populates="note",
        cascade="all, delete-orphan",
    )


class NoteImport(Base):
    """Marks a Note as created by the notes importer, and when it last wrote it.

    One row per imported note — note_id IS the primary key. `imported_at` is
    copied from the note's own `update_timestamp` right after the importer's
    last write, so `note.update_timestamp > imported_at` means a user edited
    the note after the import (see `adapters/notes_import.py`). Notes created
    any other way have no row.
    """

    __tablename__ = "note_imports"
    __table_args__ = {"schema": "assistant"}  # noqa: RUF012

    note_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant.notes.id", ondelete="CASCADE"),
        primary_key=True,
    )
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_path: Mapped[str] = mapped_column(String(1024), nullable=False)

    note: Mapped[Note] = relationship("Note", back_populates="import_record")


class NoteSearchIndex(Base):
    """Keyword search index entry for one note (title + whole body).

    Stored apart from the note on purpose: notes carry no search data, and
    the index can be dropped and rebuilt (`assistant.cli.reindex_search`)
    without touching them. Maintained only by
    `assistant.search.indexer.index_note`; there is deliberately no ORM
    relationship from `Note`. Rows are deleted with their note by the
    database (ON DELETE CASCADE).

    `title` and `body` hold analyzed tokens joined by spaces. On Postgres a
    generated, GIN-indexed `search_vector` tsvector column (title weighted A,
    body B) is derived from them — it is not mapped here, see the
    add_search_index migration.
    """

    __tablename__ = "note_search_index"
    __table_args__ = {"schema": "assistant"}  # noqa: RUF012

    note_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant.notes.id", ondelete="CASCADE"),
        primary_key=True,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # `assistant.search.analysis.SEARCH_INDEX_VERSION` this entry was built with.
    index_version: Mapped[int] = mapped_column(Integer, nullable=False)


class NodeSearchIndex(Base):
    """Keyword search index entry for one block of a note.

    Used to pick a matching note's snippet blocks. Like `NoteSearchIndex`,
    maintained only by `index_note`, with no ORM relationship from `Node`,
    and deleted with its node or note by the database. `note_id` is
    denormalized so a note's entries are found without joining `nodes`.

    `text` holds analyzed tokens joined by spaces; Postgres derives a
    generated, GIN-indexed `search_vector` from it (not mapped here).
    """

    __tablename__ = "node_search_index"
    __table_args__ = (
        Index("ix_node_search_index_note_id", "note_id"),
        {"schema": "assistant"},
    )

    node_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant.nodes.id", ondelete="CASCADE"),
        primary_key=True,
    )
    note_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant.notes.id", ondelete="CASCADE"),
        nullable=False,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")


class NoteVectorIndex(Base):
    """Tracks whether a note's embeddings are up to date.

    The embeddings themselves live in `assistant.note_chunk_embedding`, a
    Postgres-only table (pgvector) created by the add_vector_index migration
    and not mapped here; see `assistant.vectors`. One row per note, deleted
    with it by the database (ON DELETE CASCADE). There is deliberately no
    ORM relationship from `Note`.

    A note needs (re)embedding when it has no row, `indexed_at` is null,
    `index_version` is older than `VECTOR_INDEX_VERSION`, or it was marked
    stale after it was last indexed (`stale_since > indexed_at`).
    """

    __tablename__ = "note_vector_index"
    __table_args__ = {"schema": "assistant"}  # noqa: RUF012

    note_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant.notes.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # SHA-256 of the embedded chunk texts; equal hashes skip the embedding call.
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # `assistant.vectors.indexer.VECTOR_INDEX_VERSION` this entry was built with.
    index_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # When the indexer read the note it embedded (not when it finished).
    indexed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Last time a write changed what the note's embeddings should contain.
    stale_since: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Tag(Base):
    """A user's tag. Each user has their own tag vocabulary.

    `name` is the trimmed display name, keeping the casing it was created
    with. `normalized_name` (trimmed + casefolded) carries the per-owner
    uniqueness so "Work" and " work" resolve to the same tag.
    """

    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint("owner_id", "normalized_name", name="uq_tag_owner_name"),
        {"schema": "assistant"},
    )

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid_module.uuid4,
    )
    owner_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant.users.uid"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    owner: Mapped[User] = relationship("User", back_populates="tags")
    note_links: Mapped[list[NoteTag]] = relationship(
        "NoteTag",
        back_populates="tag",
        cascade="all, delete-orphan",
    )
    post_links: Mapped[list[PostTag]] = relationship(
        "PostTag",
        back_populates="tag",
        cascade="all, delete-orphan",
    )


class NoteTag(Base):
    """Links a Note to a Tag (m:n). The composite PK makes a note's tags a set.

    Tags are per-user: a user only sees the links to their own tags. The
    service layer only links a tag to a note its owner can view.
    """

    __tablename__ = "note_tags"
    __table_args__ = (
        Index("ix_note_tags_tag_id", "tag_id"),
        {"schema": "assistant"},
    )

    note_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant.notes.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant.tags.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    note: Mapped[Note] = relationship("Note", back_populates="tag_links")
    tag: Mapped[Tag] = relationship("Tag", back_populates="note_links")


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
    position: Mapped[str] = mapped_column(String(2048), nullable=False)
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


class ChatThread(Base):
    """One Ask AI conversation of a user.

    Only the listing data lives here: the messages are langgraph checkpoints
    (`PostgresSaver`, in the `public` schema) keyed by this row's id as the
    thread id. See `assistant.chat.service`.
    """

    __tablename__ = "chat_threads"
    __table_args__ = (
        Index("ix_chat_threads_user_id_updated_at", "user_id", "updated_at"),
        {"schema": "assistant"},
    )

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid_module.uuid4,
    )
    user_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant.users.uid", ondelete="CASCADE"),
        nullable=False,
    )
    # Empty until the first question, which becomes the title.
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    # Last question asked; threads are listed most recent first.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    user: Mapped[User] = relationship("User", back_populates="chat_threads")


class Category(Base):
    """A user's single-level folder, shared by blog sources and reading links.

    `description` is free text the reading list's model reads to choose a
    category for a link.
    """

    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_category_owner_name"),
        {"schema": "assistant"},
    )

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid_module.uuid4,
    )
    owner_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant.users.uid", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    owner: Mapped[User] = relationship("User", back_populates="categories")


class BlogSource(Base):
    """A blog or feed one user collects posts from.

    Nothing is shared: two users registering the same blog get two sources.
    `collect_since` is set at creation and never edited. A source with
    `archived_at` set no longer collects and only keeps its useful posts; the
    partial unique index lets its feed be registered again.
    `kind` is validated in the service layer, like `Node.node_type`.
    """

    __tablename__ = "blog_sources"
    __table_args__ = (
        Index(
            "uq_blog_source_owner_feed_url",
            "owner_id",
            "feed_url",
            unique=True,
            postgresql_where=text("archived_at IS NULL"),
            sqlite_where=text("archived_at IS NULL"),
        ),
        {"schema": "assistant"},
    )

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid_module.uuid4,
    )
    owner_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant.users.uid", ondelete="CASCADE"),
        nullable=False,
    )
    category_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant.categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    # What the user typed, and what it resolved to.
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    feed_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    preferences: Mapped[str | None] = mapped_column(Text, nullable=True)
    collect_since: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    etag: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    last_modified: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    owner: Mapped[User] = relationship("User", back_populates="blog_sources")
    category: Mapped[Category | None] = relationship("Category")
    posts: Mapped[list[BlogPost]] = relationship(
        "BlogPost",
        back_populates="source",
        cascade="all, delete-orphan",
    )
    runs: Mapped[list[BlogCollectionRun]] = relationship(
        "BlogCollectionRun",
        back_populates="source",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class BlogPost(Base):
    """One post of a source: metadata and analysis.

    The full text is not here: it is a file in the documents directory, see
    `assistant.blogs.text_store`. `status` is the pipeline's progress and
    `state` the user's verdict; `status`, `state`, `match_level` and
    `embed_status` are validated in the service layer. `read_at` is when the
    user marked the post read, independent of the verdict.
    """

    __tablename__ = "blog_posts"
    __table_args__ = (
        UniqueConstraint("source_id", "post_key", name="uq_blog_post_source_key"),
        Index(
            "ix_blog_posts_source_state_published", "source_id", "state", "published_at"
        ),
        {"schema": "assistant"},
    )

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid_module.uuid4,
    )
    source_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant.blog_sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    # See `assistant.blogs.identity.post_key`.
    post_key: Mapped[str] = mapped_column(String(64), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    match_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    motivation: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=BlogPostStatus.PENDING.value
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    state: Mapped[str] = mapped_column(
        String(20), nullable=False, default=BlogPostState.NEW.value
    )
    evaluated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    embed_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=BlogEmbedStatus.NONE.value
    )
    embed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    source: Mapped[BlogSource] = relationship("BlogSource", back_populates="posts")
    tag_links: Mapped[list[PostTag]] = relationship(
        "PostTag",
        back_populates="post",
        cascade="all, delete-orphan",
    )


class BlogCollectionRun(Base):
    """One attempt at collecting a source, by the job or a manual refresh.

    `outcome` is set once the source is read, and `finished_at` once its posts
    are analyzed too. A run left unfinished by a crash is closed by the next
    one, with `interrupted`. Only the latest runs of a source are kept, see
    `assistant.blogs.runs`.
    """

    __tablename__ = "blog_collection_runs"
    __table_args__ = (
        Index("ix_blog_collection_runs_source_started", "source_id", "started_at"),
        {"schema": "assistant"},
    )

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid_module.uuid4,
    )
    source_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant.blog_sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    trigger: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    outcome: Mapped[str | None] = mapped_column(String(20), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    interrupted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Every entry the source listed; only some are kept when there are many.
    entries_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    source: Mapped[BlogSource] = relationship("BlogSource", back_populates="runs")
    entries: Mapped[list[BlogCollectionEntry]] = relationship(
        "BlogCollectionEntry",
        back_populates="run",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="BlogCollectionEntry.position",
    )


class BlogCollectionEntry(Base):
    """One entry of a run: what the source listed and what became of it.

    The analysis columns are a copy of what the model answered in this run,
    so the log still shows it after the post changes or is deleted.
    """

    __tablename__ = "blog_collection_entries"
    __table_args__ = (
        Index("ix_blog_collection_entries_run_position", "run_id", "position"),
        {"schema": "assistant"},
    )

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid_module.uuid4,
    )
    run_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant.blog_collection_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    verdict: Mapped[str] = mapped_column(String(20), nullable=False)
    post_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant.blog_posts.id", ondelete="SET NULL"),
        nullable=True,
    )
    feed_text_chars: Mapped[int | None] = mapped_column(Integer, nullable=True)
    analysis: Mapped[str | None] = mapped_column(String(20), nullable=True)
    text_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    text_chars: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    match_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    motivation: Mapped[str | None] = mapped_column(Text, nullable=True)
    analyzed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    run: Mapped[BlogCollectionRun] = relationship(
        "BlogCollectionRun", back_populates="entries"
    )


class PostTag(Base):
    """Links a BlogPost to a Tag (m:n), from the same vocabulary as notes.

    Posts have one owner, so unlike `NoteTag` a post's links are all from its
    owner's tags.
    """

    __tablename__ = "post_tags"
    __table_args__ = (
        Index("ix_post_tags_tag_id", "tag_id"),
        {"schema": "assistant"},
    )

    post_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant.blog_posts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant.tags.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    post: Mapped[BlogPost] = relationship("BlogPost", back_populates="tag_links")
    tag: Mapped[Tag] = relationship("Tag", back_populates="post_links")


def _string_enum(enum: type[Enum]) -> SqlEnum:
    """A Python enum stored as its values in a VARCHAR(20).

    No database enum type and no CHECK constraint: the column stays a plain
    string, and the ORM reads and writes enum members.
    """
    return SqlEnum(
        enum,
        native_enum=False,
        create_constraint=False,
        length=20,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )


class ReadingLink(Base):
    """A link one user saved to read or watch later.

    The content is never stored: only what the analysis derived from it.
    `analysis_status` is the pipeline's progress and `state` the user's
    decision; they and `link_type` are enum columns stored as strings. `title_edited` and
    `category_set_by_user` keep an analysis from overwriting what the user
    chose. `decided_at` is when the link was discarded or promoted.
    """

    __tablename__ = "reading_links"
    __table_args__ = (
        UniqueConstraint("owner_id", "url_key", name="uq_reading_link_owner_url_key"),
        Index(
            "ix_reading_links_owner_state_category_created",
            "owner_id",
            "state",
            "category_id",
            "created_at",
        ),
        {"schema": "assistant"},
    )

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid_module.uuid4,
    )
    owner_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant.users.uid", ondelete="CASCADE"),
        nullable=False,
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    # See `assistant.reading.service.url_key`.
    url_key: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    title_edited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    link_type: Mapped[ReadingLinkType | None] = mapped_column(
        _string_enum(ReadingLinkType), nullable=True
    )
    category_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant.categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    category_set_by_user: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_status: Mapped[ReadingAnalysisStatus] = mapped_column(
        _string_enum(ReadingAnalysisStatus),
        nullable=False,
        default=ReadingAnalysisStatus.PENDING,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Generic, never anything from the response or the model provider.
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[ReadingLinkState] = mapped_column(
        _string_enum(ReadingLinkState),
        nullable=False,
        default=ReadingLinkState.TO_READ,
    )
    note_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant.notes.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    owner: Mapped[User] = relationship("User", back_populates="reading_links")
    category: Mapped[Category | None] = relationship("Category")
