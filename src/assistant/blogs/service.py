"""Blog directories, sources and posts of one user.

Nothing here is shared, so there are no entitlements: every function takes
the owner and loads rows filtered by it, and someone else's row is simply not
found. Nothing commits: callers own the transaction.

The post list is paged by keyset, not offset: evaluated posts leave the New
list while the user scrolls, and an offset would skip the posts after them.
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Any, TypedDict

from sqlalchemy import and_, case, delete, func, or_, select, update
from sqlalchemy.orm import contains_eager

from assistant.blogs.discovery import resolve_source
from assistant.blogs.exceptions import (
    BlogNotFoundError,
    DuplicateDirectoryError,
    DuplicateSourceError,
    InvalidPostQueryError,
)
from assistant.blogs.store import delete_post_chunks
from assistant.models.schema import (
    BlogDirectory,
    BlogEmbedStatus,
    BlogMatchLevel,
    BlogPost,
    BlogPostState,
    BlogPostStatus,
    BlogSource,
    PostTag,
    Tag,
)
from assistant.notes.tags import find_or_create_tag, get_tag

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy import ColumnElement, Select
    from sqlalchemy.orm import Session

    from assistant.models.schema import User

DEFAULT_LOOKBACK_DAYS = 7
MAX_BULK_POSTS = 500

# `pending` posts wait for analysis and `skipped` ones are not posts at all.
_VISIBLE_STATUSES = (BlogPostStatus.PROCESSED.value, BlogPostStatus.FAILED.value)
# High first, unscored last.
_MATCH_RANKS = {
    BlogMatchLevel.HIGH.value: 0,
    BlogMatchLevel.MEDIUM.value: 1,
    BlogMatchLevel.LOW.value: 2,
}
_UNSCORED_RANK = len(_MATCH_RANKS)
_rank_column = case(_MATCH_RANKS, value=BlogPost.match_level, else_=_UNSCORED_RANK)


class PostView(StrEnum):
    """Which posts a list shows."""

    ALL = "all"
    RELEVANT = "relevant"
    NEW = "new"


@dataclass(frozen=True, slots=True)
class PostFilters:
    """What narrows a post list. All of them are the caller's own."""

    directory_id: uuid.UUID | None = None
    unfiled: bool = False
    source_id: uuid.UUID | None = None
    tag_id: uuid.UUID | None = None
    # True only read posts, False only those still to read, None both.
    read: bool | None = None


@dataclass(frozen=True, slots=True)
class PostPage:
    """One page of posts, and the cursor of the next one if there is more."""

    posts: list[BlogPost]
    tags: dict[uuid.UUID, list[Tag]]
    next_cursor: str | None


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


# --- Listing posts ---


def _encode_cursor(view: PostView, post: BlogPost) -> str:
    key: list[str | int] = [post.published_at.isoformat(), str(post.id)]
    if view is PostView.NEW:
        key.append(_MATCH_RANKS.get(post.match_level or "", _UNSCORED_RANK))
    return base64.urlsafe_b64encode(json.dumps(key).encode()).decode()


def _decode_cursor(view: PostView, cursor: str) -> tuple[datetime, uuid.UUID, int]:
    """Read a cursor. A client can send anything, so nothing is assumed.

    Returns:
        (published_at, post id, match rank). The rank is only meaningful in
        the New view.

    Raises:
        InvalidPostQueryError: If the cursor was not made for this view.
    """
    msg = "This cursor is not valid"
    expected = 3 if view is PostView.NEW else 2
    try:
        key: Any = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        if isinstance(key, list) and len(key) == expected:
            rank = int(key[2]) if view is PostView.NEW else 0
            return datetime.fromisoformat(key[0]), uuid.UUID(key[1]), rank
    except (binascii.Error, ValueError, TypeError, AttributeError) as exc:
        raise InvalidPostQueryError(msg) from exc
    raise InvalidPostQueryError(msg)


def _after_cursor(view: PostView, cursor: str) -> ColumnElement[bool]:
    """The rows after a cursor, in the view's order."""
    published_at, post_id, rank = _decode_cursor(view, cursor)
    newer_first = or_(
        BlogPost.published_at < published_at,
        and_(BlogPost.published_at == published_at, BlogPost.id < post_id),
    )
    if view is not PostView.NEW:
        return newer_first
    return or_(_rank_column > rank, and_(_rank_column == rank, newer_first))


def _filtered(
    session: Session,
    owner: User,
    stmt: Select[tuple[BlogPost]],
    filters: PostFilters,
) -> Select[tuple[BlogPost]]:
    """Apply filters, refusing anything that is not the caller's.

    Raises:
        InvalidPostQueryError: If the directory and Unfiled are both asked for.
        BlogNotFoundError: If a directory or source is not the caller's.
        TagNotFoundError: If a tag is not the caller's.
    """
    if filters.directory_id is not None and filters.unfiled:
        msg = "Choose a directory or Unfiled, not both"
        raise InvalidPostQueryError(msg)
    if filters.directory_id is not None:
        get_directory(session, owner, filters.directory_id)
        stmt = stmt.where(BlogSource.directory_id == filters.directory_id)
    if filters.unfiled:
        stmt = stmt.where(BlogSource.directory_id.is_(None))
    if filters.source_id is not None:
        source = session.get(BlogSource, filters.source_id)
        if source is None or source.owner_id != owner.uid:
            raise BlogNotFoundError(str(filters.source_id))
        stmt = stmt.where(BlogPost.source_id == filters.source_id)
    if filters.tag_id is not None:
        get_tag(session, owner, filters.tag_id)
        stmt = stmt.join(PostTag, PostTag.post_id == BlogPost.id).where(
            PostTag.tag_id == filters.tag_id
        )
    if filters.read is True:
        stmt = stmt.where(BlogPost.read_at.is_not(None))
    elif filters.read is False:
        stmt = stmt.where(BlogPost.read_at.is_(None))
    return stmt


def list_posts(  # noqa: PLR0913
    session: Session,
    owner: User,
    *,
    view: PostView = PostView.ALL,
    filters: PostFilters | None = None,
    cursor: str | None = None,
    limit: int = 20,
) -> PostPage:
    """Return a page of `owner`'s posts.

    All and Relevant are newest first. New is by match level (high first,
    unscored last), then newest. Posts waiting for analysis are never listed.

    Args:
        session: The session.
        owner: The user.
        view: Which posts.
        filters: What to narrow them by.
        cursor: `next_cursor` of the previous page.
        limit: Page size.

    Returns:
        The page.

    Raises:
        InvalidPostQueryError: On a bad cursor or conflicting filters.
        BlogNotFoundError: If a filter names someone else's directory or source.
        TagNotFoundError: If a filter names someone else's tag.
    """
    stmt = (
        select(BlogPost)
        .join(BlogPost.source)
        .options(contains_eager(BlogPost.source))
        .where(
            BlogSource.owner_id == owner.uid,
            BlogPost.status.in_(_VISIBLE_STATUSES),
        )
    )
    if view is PostView.RELEVANT:
        stmt = stmt.where(BlogPost.state == BlogPostState.USEFUL.value)
    elif view is PostView.NEW:
        stmt = stmt.where(BlogPost.state == BlogPostState.NEW.value)
    stmt = _filtered(session, owner, stmt, filters or PostFilters())
    if cursor is not None:
        stmt = stmt.where(_after_cursor(view, cursor))
    if view is PostView.NEW:
        stmt = stmt.order_by(_rank_column)
    stmt = stmt.order_by(BlogPost.published_at.desc(), BlogPost.id.desc())

    rows = list(session.scalars(stmt.limit(limit + 1)))
    posts = rows[:limit]
    return PostPage(
        posts=posts,
        tags=tags_for_posts(session, [post.id for post in posts]),
        next_cursor=_encode_cursor(view, posts[-1]) if len(rows) > limit else None,
    )


# --- Verdicts ---


def _apply_state(session: Session, post: BlogPost, state: BlogPostState) -> None:
    """Move a post to a state, keeping its embeddings in step.

    Becoming useful only asks for embeddings, which the job writes. Leaving
    useful deletes them right away, in the same transaction, and the job
    checks the verdict again under a lock before writing, so a change made
    while it was calling OpenAI wins.
    """
    if post.state == state.value:
        return
    was_useful = post.state == BlogPostState.USEFUL.value
    post.state = state.value
    post.evaluated_at = None if state is BlogPostState.NEW else datetime.now(UTC)
    if state is BlogPostState.USEFUL:
        post.embed_status = BlogEmbedStatus.PENDING.value
    elif was_useful:
        delete_post_chunks(session, post.id)
        post.embed_status = BlogEmbedStatus.NONE.value
    post.embed_attempts = 0


def _owned_posts(
    session: Session, owner: User, post_ids: Sequence[uuid.UUID]
) -> list[BlogPost]:
    """Lock and return visible posts of `owner`, in id order to avoid deadlocks.

    Raises:
        BlogNotFoundError: If any of them is missing, someone else's, or not
            visible to the API.
    """
    unique_ids = sorted(set(post_ids))
    stmt = (
        select(BlogPost)
        .join(BlogPost.source)
        .options(contains_eager(BlogPost.source))
        .where(
            BlogPost.id.in_(unique_ids),
            BlogSource.owner_id == owner.uid,
            BlogPost.status.in_(_VISIBLE_STATUSES),
        )
        .order_by(BlogPost.id)
        .with_for_update(of=BlogPost)
    )
    posts = list(session.scalars(stmt))
    if len(posts) != len(unique_ids):
        msg = "Post not found"
        raise BlogNotFoundError(msg)
    return posts


def set_post_state(
    session: Session, owner: User, post_id: uuid.UUID, state: BlogPostState
) -> BlogPost:
    """Set a post's verdict. Going back to `new` is what undo does.

    Raises:
        BlogNotFoundError: If the post is missing or someone else's.
    """
    [post] = _owned_posts(session, owner, [post_id])
    _apply_state(session, post, state)
    session.flush()
    return post


def set_posts_state(
    session: Session,
    owner: User,
    post_ids: Sequence[uuid.UUID],
    state: BlogPostState,
) -> int:
    """Set the verdict of the posts the user has on screen.

    The ids are explicit, so this can't touch a post the user has not seen.
    All of them change or none.

    Returns:
        The number of posts.

    Raises:
        BlogNotFoundError: If any post is missing or someone else's.
    """
    posts = _owned_posts(session, owner, post_ids)
    for post in posts:
        _apply_state(session, post, state)
    session.flush()
    return len(posts)


# --- Read ---


def set_post_read(
    session: Session, owner: User, post_id: uuid.UUID, *, read: bool
) -> BlogPost:
    """Mark a post read or still to read. Idempotent, and the verdict stays.

    Marking a read post read again keeps the first time it was read.

    Raises:
        BlogNotFoundError: If the post is missing or someone else's.
    """
    [post] = _owned_posts(session, owner, [post_id])
    if not read:
        post.read_at = None
    elif post.read_at is None:
        post.read_at = datetime.now(UTC)
    session.flush()
    return post


# --- Tags ---


def tags_for_posts(
    session: Session, post_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[Tag]]:
    """Return the tags on each post, by name. Posts with none are absent.

    Does not check ownership: callers pass posts they loaded for their owner.
    """
    if not post_ids:
        return {}
    stmt = (
        select(PostTag.post_id, Tag)
        .join(Tag, Tag.id == PostTag.tag_id)
        .where(PostTag.post_id.in_(post_ids))
        .order_by(Tag.normalized_name)
    )
    result: dict[uuid.UUID, list[Tag]] = defaultdict(list)
    for post_id, tag in session.execute(stmt).tuples():
        result[post_id].append(tag)
    return dict(result)


def add_tag_to_post(
    session: Session,
    owner: User,
    post_id: uuid.UUID,
    *,
    tag_id: uuid.UUID | None = None,
    name: str | None = None,
) -> Tag:
    """Tag a post with one of `owner`'s tags. Idempotent.

    Exactly one of `tag_id` (an existing tag) or `name` (found or created on
    the fly) must be given.

    Raises:
        ValueError: If both or neither are given.
        BlogNotFoundError: If the post is missing or someone else's.
        TagNotFoundError: If `tag_id` is not one of `owner`'s tags.
        InvalidTagNameError: If `name` is invalid.
    """
    if (tag_id is None) == (name is None):
        msg = "Exactly one of tag_id or name must be given"
        raise ValueError(msg)
    [post] = _owned_posts(session, owner, [post_id])
    if tag_id is not None:
        tag = get_tag(session, owner, tag_id)
    else:
        assert name is not None
        tag, _ = find_or_create_tag(session, owner, name)
    if session.get(PostTag, (post.id, tag.id)) is None:
        session.add(PostTag(post_id=post.id, tag_id=tag.id))
    session.flush()
    return tag


def remove_tag_from_post(
    session: Session, owner: User, post_id: uuid.UUID, tag_id: uuid.UUID
) -> None:
    """Remove one of `owner`'s tags from a post. Idempotent.

    Raises:
        BlogNotFoundError: If the post is missing or someone else's.
        TagNotFoundError: If `tag_id` is not one of `owner`'s tags.
    """
    [post] = _owned_posts(session, owner, [post_id])
    get_tag(session, owner, tag_id)
    link = session.get(PostTag, (post.id, tag_id))
    if link is not None:
        session.delete(link)
        session.flush()
