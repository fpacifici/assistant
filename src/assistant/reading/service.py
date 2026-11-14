"""Reading links of one user.

Nothing here is shared, so there are no entitlements: every function takes
the owner and loads rows filtered by it, and someone else's link is simply
not found. Nothing commits: callers own the transaction.

Lists are paged by keyset, not offset: links leave a view as the user decides
on them, and an offset would skip the links after them. To read is oldest
first, by `created_at`; Archive and Promoted most recently decided first, by
`decided_at`.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, TypedDict
from urllib.parse import urlsplit

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import selectinload

from assistant.categories.service import get_category
from assistant.models.schema import (
    Note,
    PermissionName,
    ReadingAnalysisStatus,
    ReadingLink,
    ReadingLinkState,
)
from assistant.notes.permissions import editable_scope, require_note_access
from assistant.notes.service import create_note
from assistant.reading.exceptions import (
    DuplicateLinkError,
    InvalidLinkQueryError,
    InvalidLinkStateError,
    InvalidLinkUrlError,
    LinkNotFoundError,
)
from assistant.reading.worker import queue_for_analysis
from assistant.text import blank_to_none
from assistant.web.urls import canonical_path, is_http_url, strip_tracking

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy import ColumnElement, Select, UnaryExpression
    from sqlalchemy.orm import InstrumentedAttribute, Session

    from assistant.models.schema import User
    from assistant.vectors.search import NoteSearcher

MAX_URL_LENGTH = 2048
MAX_TITLE_LENGTH = 1024
MAX_SUGGESTIONS = 5
# Chunks fetched for suggestions: several can come from one note.
SUGGESTION_CHUNKS = 20
MAX_PASSAGE_CHARS = 300

_DEFAULT_PORTS = {"http": 80, "https": 443}
# What each action can start from.
_DISCARDABLE = frozenset({ReadingLinkState.TO_READ})
_RESTORABLE = frozenset({ReadingLinkState.DISCARDED})
_DELETABLE = frozenset({ReadingLinkState.DISCARDED, ReadingLinkState.PROMOTED})
_PROMOTABLE = frozenset({ReadingLinkState.TO_READ})
# A cursor is the last link's sort value and id: JSON, then base64.
_CURSOR = TypeAdapter(tuple[datetime, uuid.UUID])


@dataclass(frozen=True, slots=True)
class LinkFilters:
    """What narrows a link list. A category must be the caller's own."""

    category_id: uuid.UUID | None = None
    unfiled: bool = False


@dataclass(frozen=True, slots=True)
class LinkPage:
    """One page of links, and the cursor of the next one if there is more."""

    links: list[ReadingLink]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class NoteSuggestion:
    """A note the user can edit that talks about the link's topic."""

    note_id: uuid.UUID
    notebook_id: uuid.UUID
    title: str
    notebook_name: str
    passage: str


class LinkChanges(TypedDict, total=False):
    """Editable link fields. A missing key leaves the field as it is."""

    title: str | None
    category_id: uuid.UUID | None
    user_notes: str | None


# --- URLs ---


def normalize_url(url: str) -> str:
    """The URL to store: trimmed, with tracking parameters dropped.

    Raises:
        InvalidLinkUrlError: If it is not an absolute http(s) URL.
    """
    url = url.strip()
    if len(url) > MAX_URL_LENGTH or not is_http_url(url):
        raise InvalidLinkUrlError
    try:
        hostname = urlsplit(url).hostname
    except ValueError as exc:
        raise InvalidLinkUrlError from exc
    if not hostname:
        raise InvalidLinkUrlError
    return strip_tracking(url)


def url_key(url: str) -> str:
    """The identity of a link: the same for spelling variants of one URL.

    Like a blog post's key (`assistant.web.urls.canonical_path`), it ignores tracking
    parameters, the order of the others, a trailing slash and the fragment,
    but it keeps the host, since links come from many sites. The scheme and
    a default port are ignored.

    Returns:
        A hex SHA-256 digest.
    """
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    port = parts.port
    if port is not None and port != _DEFAULT_PORTS.get(parts.scheme.lower()):
        host = f"{host}:{port}"
    return hashlib.sha256(f"{host}{canonical_path(url)}".encode()).hexdigest()


# --- Reading and adding ---


def get_link(
    session: Session, owner: User, link_id: uuid.UUID, *, lock: bool = False
) -> ReadingLink:
    """Return one of `owner`'s links.

    Args:
        session: The session.
        owner: The user.
        link_id: The link.
        lock: Lock the row until the transaction ends, before changing it.

    Raises:
        LinkNotFoundError: If it is missing or someone else's.
    """
    stmt = select(ReadingLink).where(
        ReadingLink.id == link_id, ReadingLink.owner_id == owner.uid
    )
    if lock:
        stmt = stmt.with_for_update()
    link = session.scalar(stmt)
    if link is None:
        raise LinkNotFoundError(str(link_id))
    return link


def add_link(session: Session, owner: User, url: str) -> ReadingLink:
    """Save a URL as a link to read. It is analyzed once the transaction commits.

    Raises:
        InvalidLinkUrlError: If it is not an absolute http(s) URL.
        DuplicateLinkError: If `owner` already has it, in any state.
    """
    normalized = normalize_url(url)
    key = url_key(normalized)
    existing = session.scalar(
        select(ReadingLink.id).where(
            ReadingLink.owner_id == owner.uid, ReadingLink.url_key == key
        ),
    )
    if existing is not None:
        raise DuplicateLinkError(existing)
    link = ReadingLink(owner_id=owner.uid, url=normalized, url_key=key)
    session.add(link)
    session.flush()
    queue_for_analysis(session, link.id)
    return link


def retry_analysis(session: Session, owner: User, link_id: uuid.UUID) -> ReadingLink:
    """Analyze a link again, in any state, after the transaction commits.

    Attempts start over. What the user chose wins, as on the first analysis:
    an edited title and a category they set (Unfiled included) are kept, so
    only a link the AI filed is filed again.

    Raises:
        LinkNotFoundError: If the link is missing or someone else's.
    """
    link = get_link(session, owner, link_id, lock=True)
    link.analysis_status = ReadingAnalysisStatus.PENDING
    link.attempts = 0
    link.last_error = None
    session.flush()
    queue_for_analysis(session, link.id)
    return link


# --- Listing ---


@dataclass(frozen=True, slots=True)
class _ViewOrder:
    """How a view sorts: a time column, a direction, and its value on a link.

    The link id breaks ties, in the same direction.
    """

    column: InstrumentedAttribute[datetime] | InstrumentedAttribute[datetime | None]
    ascending: bool
    sort_value: Callable[[ReadingLink], datetime | None]

    def order_by(
        self,
    ) -> tuple[
        UnaryExpression[datetime] | UnaryExpression[datetime | None],
        UnaryExpression[uuid.UUID],
    ]:
        """The ORDER BY clauses: the time column, then the id."""
        if self.ascending:
            return self.column.asc(), ReadingLink.id.asc()
        return self.column.desc(), ReadingLink.id.desc()

    def encode(self, link: ReadingLink) -> str:
        value = self.sort_value(link)
        assert value is not None  # decided links have a decision time
        return base64.urlsafe_b64encode(_CURSOR.dump_json((value, link.id))).decode()

    def after(self, cursor: str) -> ColumnElement[bool]:
        """The rows after a cursor, in this order.

        Raises:
            InvalidLinkQueryError: If the cursor is not valid.
        """
        try:
            value, link_id = _CURSOR.validate_json(base64.urlsafe_b64decode(cursor))
        except (binascii.Error, ValueError, ValidationError) as exc:
            msg = "This cursor is not valid"
            raise InvalidLinkQueryError(msg) from exc
        if self.ascending:
            return or_(
                self.column > value,
                and_(self.column == value, ReadingLink.id > link_id),
            )
        return or_(
            self.column < value, and_(self.column == value, ReadingLink.id < link_id)
        )


# To read: by when the link was added, oldest first. The others: by the
# decision, most recent first.
_DECIDED = _ViewOrder(ReadingLink.decided_at, False, lambda link: link.decided_at)
_ORDERS = {
    ReadingLinkState.TO_READ: _ViewOrder(
        ReadingLink.created_at, True, lambda link: link.created_at
    ),
    ReadingLinkState.DISCARDED: _DECIDED,
    ReadingLinkState.PROMOTED: _DECIDED,
}


def _filtered(
    session: Session,
    owner: User,
    stmt: Select[tuple[ReadingLink]],
    filters: LinkFilters,
) -> Select[tuple[ReadingLink]]:
    """Apply filters, refusing a category that is not the caller's.

    Raises:
        InvalidLinkQueryError: If a category and Unfiled are both asked for.
        CategoryNotFoundError: If the category is not the caller's.
    """
    if filters.category_id is not None and filters.unfiled:
        msg = "Choose a category or Unfiled, not both"
        raise InvalidLinkQueryError(msg)
    if filters.category_id is not None:
        get_category(session, owner, filters.category_id)
        stmt = stmt.where(ReadingLink.category_id == filters.category_id)
    if filters.unfiled:
        stmt = stmt.where(ReadingLink.category_id.is_(None))
    return stmt


def list_links(  # noqa: PLR0913
    session: Session,
    owner: User,
    *,
    state: ReadingLinkState = ReadingLinkState.TO_READ,
    filters: LinkFilters | None = None,
    cursor: str | None = None,
    limit: int = 20,
) -> LinkPage:
    """Return a page of `owner`'s links in one state.

    To read is oldest first; Archive and Promoted most recently decided first.

    Raises:
        InvalidLinkQueryError: On a bad cursor or conflicting filters.
        CategoryNotFoundError: If a filter names someone else's category.
    """
    order = _ORDERS[state]
    stmt = (
        select(ReadingLink)
        .options(selectinload(ReadingLink.note))
        .where(ReadingLink.owner_id == owner.uid, ReadingLink.state == state)
    )
    stmt = _filtered(session, owner, stmt, filters or LinkFilters())
    if cursor is not None:
        stmt = stmt.where(order.after(cursor))
    rows = list(session.scalars(stmt.order_by(*order.order_by()).limit(limit + 1)))
    links = rows[:limit]
    return LinkPage(
        links=links,
        next_cursor=order.encode(links[-1]) if len(rows) > limit else None,
    )


def link_counts(
    session: Session, owner: User, state: ReadingLinkState
) -> dict[uuid.UUID | None, int]:
    """How many of `owner`'s links in a state each category has.

    Returns:
        Counts by category id, `None` for Unfiled. Categories with no link
        are absent.
    """
    stmt = (
        select(ReadingLink.category_id, func.count(ReadingLink.id))
        .where(ReadingLink.owner_id == owner.uid, ReadingLink.state == state)
        .group_by(ReadingLink.category_id)
    )
    return dict(session.execute(stmt).tuples().all())


# --- Editing ---


def update_link(
    session: Session, owner: User, link_id: uuid.UUID, changes: LinkChanges
) -> ReadingLink:
    """Edit a link's title, category or notes, in any state.

    A title or a category set here wins over the analysis, now and on
    retries: a blank title goes back to the automatic one, though, and the
    next analysis may set it.

    Raises:
        LinkNotFoundError: If the link is missing or someone else's.
        CategoryNotFoundError: If the category is missing or someone else's.
    """
    link = get_link(session, owner, link_id, lock=True)
    if "title" in changes:
        title = blank_to_none(changes["title"])
        link.title = title[:MAX_TITLE_LENGTH] if title else None
        link.title_edited = title is not None
    if "category_id" in changes:
        category_id = changes["category_id"]
        if category_id is not None:
            get_category(session, owner, category_id)
        link.category_id = category_id
        link.category_set_by_user = True
    if "user_notes" in changes:
        link.user_notes = blank_to_none(changes["user_notes"])
    session.flush()
    return link


# --- Decisions ---


_STATE_LABELS = {
    ReadingLinkState.TO_READ: "still to read",
    ReadingLinkState.DISCARDED: "in the archive",
    ReadingLinkState.PROMOTED: "promoted",
}


def _require_state(
    link: ReadingLink, allowed: frozenset[ReadingLinkState], action: str
) -> None:
    if link.state not in allowed:
        label = _STATE_LABELS[link.state]
        msg = f"This link is {label}: it can't be {action}"
        raise InvalidLinkStateError(msg)


def discard_link(session: Session, owner: User, link_id: uuid.UUID) -> ReadingLink:
    """Move a link to read to the Archive.

    Raises:
        LinkNotFoundError: If the link is missing or someone else's.
        InvalidLinkStateError: If it is not to read.
    """
    link = get_link(session, owner, link_id, lock=True)
    _require_state(link, _DISCARDABLE, "discarded")
    link.state = ReadingLinkState.DISCARDED
    link.decided_at = datetime.now(UTC)
    session.flush()
    return link


def restore_link(session: Session, owner: User, link_id: uuid.UUID) -> ReadingLink:
    """Move a discarded link back to read.

    Raises:
        LinkNotFoundError: If the link is missing or someone else's.
        InvalidLinkStateError: If it is not discarded. Promotion is final.
    """
    link = get_link(session, owner, link_id, lock=True)
    _require_state(link, _RESTORABLE, "restored")
    link.state = ReadingLinkState.TO_READ
    link.decided_at = None
    session.flush()
    return link


def delete_link(session: Session, owner: User, link_id: uuid.UUID) -> None:
    """Delete a discarded or promoted link. A promoted link's note stays.

    Raises:
        LinkNotFoundError: If the link is missing or someone else's.
        InvalidLinkStateError: If it is still to read: discard it first.
    """
    link = get_link(session, owner, link_id, lock=True)
    _require_state(link, _DELETABLE, "deleted")
    session.delete(link)
    session.flush()


# --- Promotion ---


def _passage(text: str) -> str:
    single = " ".join(text.split())
    if len(single) <= MAX_PASSAGE_CHARS:
        return single
    return single[: MAX_PASSAGE_CHARS - 1].rstrip() + "…"


def suggest_notes(
    session: Session, owner: User, link_id: uuid.UUID, searcher: NoteSearcher
) -> list[NoteSuggestion]:
    """Up to `MAX_SUGGESTIONS` notes the user can edit about the link's topic.

    Semantic search with the summary as the query, or the title (else the
    URL) when there is none. Chunks are grouped by note, best first.

    Raises:
        LinkNotFoundError: If the link is missing or someone else's.
    """
    link = get_link(session, owner, link_id)
    query = link.summary or link.title or link.url
    scope = editable_scope(session, owner)
    if scope.is_empty:
        return []
    hits = searcher.search(session, owner, query, k=SUGGESTION_CHUNKS, scope=scope)
    suggestions: dict[uuid.UUID, NoteSuggestion] = {}
    for hit in hits:
        if hit.note_id in suggestions:
            continue
        suggestions[hit.note_id] = NoteSuggestion(
            note_id=hit.note_id,
            notebook_id=hit.notebook_id,
            title=hit.title,
            notebook_name=hit.notebook_name,
            passage=_passage(hit.content),
        )
        if len(suggestions) == MAX_SUGGESTIONS:
            break
    return list(suggestions.values())


def promote_link(  # noqa: PLR0913
    session: Session,
    owner: User,
    link_id: uuid.UUID,
    *,
    note_id: uuid.UUID | None = None,
    notebook_id: uuid.UUID | None = None,
    title: str | None = None,
) -> tuple[ReadingLink, Note]:
    """Promote a link to an existing note, or to a new one. Promotion is final.

    Nothing is written into the note: a new note has only its title.

    Args:
        session: The session.
        owner: The user.
        link_id: The link, still to read.
        note_id: An existing note the user can edit.
        notebook_id: Where to create a note, with `title`, instead.
        title: The new note's title.

    Returns:
        The link and its note.

    Raises:
        ValueError: Unless exactly one of `note_id` or `notebook_id` and
            `title` is given.
        LinkNotFoundError: If the link is missing or someone else's.
        InvalidLinkStateError: If the link is not to read.
        NoteNotFoundError, NotebookNotFoundError: If the note or notebook
            can't be seen.
        PermissionDeniedError: If the note can't be edited, or the notebook
            doesn't take new notes from the user.
    """
    creating = notebook_id is not None and bool(title and title.strip())
    if (note_id is None) == (not creating):
        msg = "Give a note, or a notebook and a title"
        raise ValueError(msg)
    link = get_link(session, owner, link_id, lock=True)
    _require_state(link, _PROMOTABLE, "promoted")
    if note_id is not None:
        note = require_note_access(session, note_id, owner, PermissionName.UPDATE)
    else:
        assert notebook_id is not None
        assert title is not None
        note = create_note(session, notebook_id, owner, title.strip())
    link.state = ReadingLinkState.PROMOTED
    link.decided_at = datetime.now(UTC)
    link.note_id = note.id
    session.flush()
    return link, note
