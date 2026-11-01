"""Blog directories, sources and posts of one user.

Nothing here is shared, so there are no entitlements: every function takes
the owner and loads rows filtered by it, and someone else's row is simply not
found. Nothing commits: callers own the transaction.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, TypedDict

from sqlalchemy import delete, func, select, update

from assistant.blogs.discovery import resolve_source
from assistant.blogs.exceptions import (
    BlogNotFoundError,
    DuplicateDirectoryError,
    DuplicateSourceError,
)
from assistant.models.schema import (
    BlogDirectory,
    BlogPost,
    BlogPostState,
    BlogSource,
)

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session

    from assistant.models.schema import User

DEFAULT_LOOKBACK_DAYS = 7


class SourceChanges(TypedDict, total=False):
    """Editable source fields. A missing key leaves the field as it is."""

    title: str
    remarks: str | None
    preferences: str | None
    directory_id: uuid.UUID | None
    enabled: bool


def _clean(text: str | None) -> str | None:
    """Blank free text means there is none."""
    stripped = text.strip() if text else ""
    return stripped or None


# --- Directories ---


def list_directories(session: Session, owner: User) -> list[BlogDirectory]:
    """Return `owner`'s directories, ordered by name, ignoring case."""
    stmt = (
        select(BlogDirectory)
        .where(BlogDirectory.owner_id == owner.uid)
        .order_by(func.lower(BlogDirectory.name), BlogDirectory.id)
    )
    return list(session.scalars(stmt))


def get_directory(
    session: Session, owner: User, directory_id: uuid.UUID
) -> BlogDirectory:
    """Return one of `owner`'s directories.

    Raises:
        BlogNotFoundError: If it is missing or someone else's.
    """
    directory = session.get(BlogDirectory, directory_id)
    if directory is None or directory.owner_id != owner.uid:
        raise BlogNotFoundError(str(directory_id))
    return directory


def _require_free_name(
    session: Session,
    owner: User,
    name: str,
    *,
    ignore: uuid.UUID | None = None,
) -> None:
    existing = session.scalar(
        select(BlogDirectory).where(
            BlogDirectory.owner_id == owner.uid, BlogDirectory.name == name
        ),
    )
    if existing is not None and existing.id != ignore:
        raise DuplicateDirectoryError(name)


def create_directory(session: Session, owner: User, name: str) -> BlogDirectory:
    """Create a directory.

    Raises:
        DuplicateDirectoryError: If `owner` already has one with this name.
    """
    _require_free_name(session, owner, name)
    directory = BlogDirectory(owner_id=owner.uid, name=name)
    session.add(directory)
    session.flush()
    return directory


def rename_directory(
    session: Session, owner: User, directory_id: uuid.UUID, name: str
) -> BlogDirectory:
    """Rename a directory.

    Raises:
        BlogNotFoundError: If it is missing or someone else's.
        DuplicateDirectoryError: If `owner` has another one with this name.
    """
    directory = get_directory(session, owner, directory_id)
    _require_free_name(session, owner, name, ignore=directory.id)
    directory.name = name
    session.flush()
    return directory


def delete_directory(session: Session, owner: User, directory_id: uuid.UUID) -> None:
    """Delete a directory. Its sources move to Unfiled.

    Raises:
        BlogNotFoundError: If it is missing or someone else's.
    """
    directory = get_directory(session, owner, directory_id)
    session.execute(
        update(BlogSource)
        .where(BlogSource.directory_id == directory.id)
        .values(directory_id=None),
    )
    session.delete(directory)
    session.flush()


# --- Sources ---


def list_sources(
    session: Session, owner: User, *, archived: bool = False
) -> list[BlogSource]:
    """Return `owner`'s sources, ordered by title, ignoring case.

    Args:
        session: The session.
        owner: The user.
        archived: Return the archived sources that still have useful posts,
            instead of the active ones. These are what the post filters
            offer; an archived source with no useful post left is not listed.
    """
    stmt = (
        select(BlogSource)
        .where(BlogSource.owner_id == owner.uid)
        .order_by(func.lower(BlogSource.title), BlogSource.id)
    )
    if archived:
        useful = select(BlogPost.id).where(
            BlogPost.source_id == BlogSource.id,
            BlogPost.state == BlogPostState.USEFUL.value,
        )
        stmt = stmt.where(BlogSource.archived_at.is_not(None), useful.exists())
    else:
        stmt = stmt.where(BlogSource.archived_at.is_(None))
    return list(session.scalars(stmt))


def get_source(session: Session, owner: User, source_id: uuid.UUID) -> BlogSource:
    """Return one of `owner`'s active sources.

    Raises:
        BlogNotFoundError: If it is missing, archived or someone else's.
    """
    source = session.get(BlogSource, source_id)
    if source is None or source.owner_id != owner.uid or source.archived_at is not None:
        raise BlogNotFoundError(str(source_id))
    return source


def useful_post_count(session: Session, source_id: uuid.UUID) -> int:
    """How many posts of a source are marked useful."""
    stmt = select(func.count(BlogPost.id)).where(
        BlogPost.source_id == source_id,
        BlogPost.state == BlogPostState.USEFUL.value,
    )
    return session.scalar(stmt) or 0


def register_source(  # noqa: PLR0913
    session: Session,
    owner: User,
    url: str,
    *,
    title: str | None = None,
    remarks: str | None = None,
    preferences: str | None = None,
    directory_id: uuid.UUID | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> BlogSource:
    """Resolve a URL and register it as a source.

    Args:
        session: The session.
        owner: The user.
        url: A feed, or a blog page.
        title: Defaults to the feed or page title.
        remarks: Free text for the user.
        preferences: What the user wants from this source.
        directory_id: One of `owner`'s directories; `None` is Unfiled.
        lookback_days: Collection starts this many days ago. Fixed from now on.

    Returns:
        The new source.

    Raises:
        BlogNotFoundError: If the directory is missing or someone else's.
        SourceResolutionError: If the URL has nothing to collect.
        DuplicateSourceError: If `owner` already registered the resolved feed.
    """
    if directory_id is not None:
        get_directory(session, owner, directory_id)
    resolved = resolve_source(url)
    existing = session.scalar(
        select(BlogSource.id).where(
            BlogSource.owner_id == owner.uid,
            BlogSource.feed_url == resolved.feed_url,
            BlogSource.archived_at.is_(None),
        ),
    )
    if existing is not None:
        raise DuplicateSourceError
    source = BlogSource(
        owner_id=owner.uid,
        directory_id=directory_id,
        url=url,
        feed_url=resolved.feed_url,
        kind=resolved.kind.value,
        title=_clean(title) or resolved.title,
        remarks=_clean(remarks),
        preferences=_clean(preferences),
        collect_since=datetime.now(UTC) - timedelta(days=lookback_days),
    )
    session.add(source)
    session.flush()
    return source


def update_source(
    session: Session,
    owner: User,
    source_id: uuid.UUID,
    changes: SourceChanges,
) -> BlogSource:
    """Edit, pause or move a source. New preferences apply to new posts only.

    Raises:
        BlogNotFoundError: If the source or the directory it moves to is
            missing or someone else's.
    """
    source = get_source(session, owner, source_id)
    if "title" in changes:
        source.title = _clean(changes["title"]) or source.title
    if "remarks" in changes:
        source.remarks = _clean(changes["remarks"])
    if "preferences" in changes:
        source.preferences = _clean(changes["preferences"])
    if "enabled" in changes:
        source.enabled = changes["enabled"]
    if "directory_id" in changes:
        directory_id = changes["directory_id"]
        if directory_id is not None:
            get_directory(session, owner, directory_id)
        source.directory_id = directory_id
    session.flush()
    return source


def delete_source(
    session: Session,
    owner: User,
    source_id: uuid.UUID,
    *,
    keep_useful: bool = False,
) -> None:
    """Delete a source, or archive it to keep its useful posts.

    An archived source stops collecting and leaves the source list, and only
    its useful posts remain. With no useful post to keep, it is just deleted.
    Text files of removed posts go in the job's next sweep.

    Raises:
        BlogNotFoundError: If it is missing, archived or someone else's.
    """
    source = get_source(session, owner, source_id)
    if keep_useful and useful_post_count(session, source.id) > 0:
        session.execute(
            delete(BlogPost).where(
                BlogPost.source_id == source.id,
                BlogPost.state != BlogPostState.USEFUL.value,
            ),
        )
        source.archived_at = datetime.now(UTC)
        source.enabled = False
    else:
        session.delete(source)
    session.flush()
