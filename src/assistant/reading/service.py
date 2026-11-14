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
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, TypedDict
from urllib.parse import urlsplit

from sqlalchemy import and_, func, or_, select

from assistant.blogs.identity import canonical_path, is_http_url, strip_tracking
from assistant.categories.service import get_category
from assistant.models.schema import ReadingLink, ReadingLinkState
from assistant.reading.exceptions import (
    DuplicateLinkError,
    InvalidLinkQueryError,
    InvalidLinkStateError,
    InvalidLinkUrlError,
    LinkNotFoundError,
)

if TYPE_CHECKING:
    from sqlalchemy import ColumnElement, Select
    from sqlalchemy.orm import Session

    from assistant.models.schema import User

MAX_URL_LENGTH = 2048
MAX_TITLE_LENGTH = 1024

_DEFAULT_PORTS = {"http": 80, "https": 443}
# What each action can start from.
_DISCARDABLE = frozenset({ReadingLinkState.TO_READ.value})
_RESTORABLE = frozenset({ReadingLinkState.DISCARDED.value})
_DELETABLE = frozenset(
    {ReadingLinkState.DISCARDED.value, ReadingLinkState.PROMOTED.value}
)


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


class LinkChanges(TypedDict, total=False):
    """Editable link fields. A missing key leaves the field as it is."""

    title: str | None
    category_id: uuid.UUID | None
    user_notes: str | None


def _clean(text: str | None) -> str | None:
    """Blank free text means there is none."""
    stripped = text.strip() if text else ""
    return stripped or None


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

    Like a blog post's key (`assistant.blogs.identity`), it ignores tracking
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
    """Save a URL as a link to read, waiting for analysis.

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
    return link


# --- Listing ---


def _sort_column(state: ReadingLinkState) -> Any:  # noqa: ANN401
    """To read sorts by when the link was added, the others by the decision."""
    if state is ReadingLinkState.TO_READ:
        return ReadingLink.created_at
    return ReadingLink.decided_at


def _encode_cursor(state: ReadingLinkState, link: ReadingLink) -> str:
    sort_value = link.created_at if state is ReadingLinkState.TO_READ else link.decided_at
    assert sort_value is not None  # decided links have a decision time
    key = [sort_value.isoformat(), str(link.id)]
    return base64.urlsafe_b64encode(json.dumps(key).encode()).decode()


def _after_cursor(state: ReadingLinkState, cursor: str) -> ColumnElement[bool]:
    """The rows after a cursor, in the view's order.

    Raises:
        InvalidLinkQueryError: If the cursor is not valid.
    """
    msg = "This cursor is not valid"
    try:
        key: Any = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        if not isinstance(key, list) or len(key) != 2:  # noqa: PLR2004
            raise InvalidLinkQueryError(msg)
        sort_value, link_id = datetime.fromisoformat(key[0]), uuid.UUID(key[1])
    except (binascii.Error, ValueError, TypeError, AttributeError) as exc:
        raise InvalidLinkQueryError(msg) from exc
    column = _sort_column(state)
    if state is ReadingLinkState.TO_READ:
        return or_(
            column > sort_value, and_(column == sort_value, ReadingLink.id > link_id)
        )
    return or_(column < sort_value, and_(column == sort_value, ReadingLink.id < link_id))


def _filtered(
    session: Session,
    owner: User,
    stmt: Select[Any],
    filters: LinkFilters,
) -> Select[Any]:
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
    stmt = select(ReadingLink).where(
        ReadingLink.owner_id == owner.uid, ReadingLink.state == state.value
    )
    stmt = _filtered(session, owner, stmt, filters or LinkFilters())
    if cursor is not None:
        stmt = stmt.where(_after_cursor(state, cursor))
    column = _sort_column(state)
    if state is ReadingLinkState.TO_READ:
        stmt = stmt.order_by(column.asc(), ReadingLink.id.asc())
    else:
        stmt = stmt.order_by(column.desc(), ReadingLink.id.desc())
    rows = list(session.scalars(stmt.limit(limit + 1)))
    links = rows[:limit]
    return LinkPage(
        links=links,
        next_cursor=_encode_cursor(state, links[-1]) if len(rows) > limit else None,
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
        .where(ReadingLink.owner_id == owner.uid, ReadingLink.state == state.value)
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
        title = _clean(changes["title"])
        link.title = title[:MAX_TITLE_LENGTH] if title else None
        link.title_edited = title is not None
    if "category_id" in changes:
        category_id = changes["category_id"]
        if category_id is not None:
            get_category(session, owner, category_id)
        link.category_id = category_id
        link.category_set_by_user = True
    if "user_notes" in changes:
        link.user_notes = _clean(changes["user_notes"])
    session.flush()
    return link


# --- Decisions ---


_STATE_LABELS = {
    ReadingLinkState.TO_READ.value: "still to read",
    ReadingLinkState.DISCARDED.value: "in the archive",
    ReadingLinkState.PROMOTED.value: "promoted",
}


def _require_state(link: ReadingLink, allowed: frozenset[str], action: str) -> None:
    if link.state not in allowed:
        label = _STATE_LABELS.get(link.state, link.state)
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
    link.state = ReadingLinkState.DISCARDED.value
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
    link.state = ReadingLinkState.TO_READ.value
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
