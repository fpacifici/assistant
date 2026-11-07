"""The collection log: what each run found at a source and what became of it.

The job and a manual refresh write a `BlogCollectionRun` per source, with one
`BlogCollectionEntry` per entry the feed or sitemap listed, and fill in the
analysis as each post goes through the model. The user reads it to see why a
post was or wasn't collected, and what the model made of it.

Only the latest `MAX_RUNS_PER_SOURCE` runs of a source are kept, and at most
`MAX_LOGGED_ENTRIES` entries of a run: a big sitemap lists thousands of pages
it has already collected, so those are the ones left out first.

Nothing commits here except where noted: callers own the transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete, func, select, update

from assistant.blogs.exceptions import BlogNotFoundError, SourcePausedError
from assistant.blogs.service import get_source
from assistant.models.schema import (
    BlogCollectionEntry,
    BlogCollectionRun,
    BlogEntryVerdict,
    BlogRunTrigger,
    BlogSource,
)

if TYPE_CHECKING:
    import uuid
    from collections.abc import Collection, Mapping, Sequence

    from sqlalchemy.orm import Session

    from assistant.models.schema import User

MAX_RUNS_PER_SOURCE = 20
MAX_LOGGED_ENTRIES = 300
_MAX_URL_LENGTH = 2048
_MAX_TITLE_LENGTH = 1024


@dataclass(frozen=True, slots=True)
class LoggedEntry:
    """One entry of a feed or sitemap and the collection's verdict on it.

    Attributes:
        url: Its link, as listed.
        verdict: What the collection made of it.
        title: Its title, if known.
        published_at: Its date, if known.
        feed_text_chars: How much text the feed gave for it.
        key: Its `post_key`, which links a new entry to its post.
    """

    url: str
    verdict: BlogEntryVerdict
    title: str | None = None
    published_at: datetime | None = None
    feed_text_chars: int | None = None
    key: str | None = None


# --- Writing ---


def start_run(
    session: Session, source_id: uuid.UUID, trigger: BlogRunTrigger
) -> BlogCollectionRun:
    """Add a run for a source, dropping its oldest runs beyond the limit."""
    keep = (
        select(BlogCollectionRun.id)
        .where(BlogCollectionRun.source_id == source_id)
        .order_by(BlogCollectionRun.started_at.desc(), BlogCollectionRun.id.desc())
        .limit(MAX_RUNS_PER_SOURCE - 1)
    )
    session.execute(
        delete(BlogCollectionRun).where(
            BlogCollectionRun.source_id == source_id,
            BlogCollectionRun.id.not_in(keep.scalar_subquery()),
        ),
    )
    run = BlogCollectionRun(source_id=source_id, trigger=trigger.value)
    session.add(run)
    session.flush()
    return run


def close_interrupted_runs(session: Session, keep: Collection[uuid.UUID] = ()) -> int:
    """Close the runs a crash left unfinished.

    Only call this holding the job's advisory lock: then no other run is
    going, so an unfinished one is dead.

    Args:
        session: The session.
        keep: Runs that belong to the caller.

    Returns:
        How many were closed.
    """
    stmt = (
        update(BlogCollectionRun)
        .where(BlogCollectionRun.finished_at.is_(None))
        .values(finished_at=datetime.now(UTC), interrupted=True)
    )
    if keep:
        stmt = stmt.where(BlogCollectionRun.id.not_in(list(keep)))
    return session.execute(stmt).rowcount  # type: ignore[attr-defined, no-any-return]


def kept_for_log(entries: Sequence[LoggedEntry]) -> list[LoggedEntry]:
    """The entries worth logging, at most `MAX_LOGGED_ENTRIES`, in order.

    Anything that happened in this run comes first; posts collected by an
    earlier run fill what room is left.
    """
    if len(entries) <= MAX_LOGGED_ENTRIES:
        return list(entries)
    chosen = [i for i, e in enumerate(entries) if e.verdict != BlogEntryVerdict.STORED]
    chosen = chosen[:MAX_LOGGED_ENTRIES]
    room = MAX_LOGGED_ENTRIES - len(chosen)
    if room:
        stored = [
            i for i, e in enumerate(entries) if e.verdict == BlogEntryVerdict.STORED
        ]
        chosen.extend(stored[:room])
    return [entries[i] for i in sorted(chosen)]


def record_entries(
    session: Session,
    run: BlogCollectionRun,
    entries: Sequence[LoggedEntry],
    post_ids: Mapping[str, uuid.UUID],
) -> None:
    """Log what a run found at its source.

    Args:
        session: The session.
        run: The run.
        entries: Every entry the source listed.
        post_ids: The posts stored in this run, by `post_key`.
    """
    run.entries_found = len(entries)
    for position, entry in enumerate(kept_for_log(entries)):
        session.add(
            BlogCollectionEntry(
                run_id=run.id,
                position=position,
                url=entry.url[:_MAX_URL_LENGTH],
                title=entry.title[:_MAX_TITLE_LENGTH] if entry.title else None,
                published_at=entry.published_at,
                verdict=entry.verdict.value,
                post_id=post_ids.get(entry.key) if entry.key else None,
                feed_text_chars=entry.feed_text_chars,
            ),
        )
    session.flush()


def entry_for_post(
    session: Session,
    run_id: uuid.UUID,
    post_id: uuid.UUID,
    *,
    url: str,
    title: str | None,
) -> BlogCollectionEntry | None:
    """The entry of a post in a run, added as a retry if the run lacks one.

    Returns:
        The entry, or `None` if the run is gone.
    """
    entry = session.scalars(
        select(BlogCollectionEntry).where(
            BlogCollectionEntry.run_id == run_id,
            BlogCollectionEntry.post_id == post_id,
        ),
    ).first()
    if entry is not None:
        return entry
    if session.get(BlogCollectionRun, run_id) is None:
        return None
    last = session.scalars(
        select(BlogCollectionEntry.position)
        .where(BlogCollectionEntry.run_id == run_id)
        .order_by(BlogCollectionEntry.position.desc())
        .limit(1),
    ).first()
    entry = BlogCollectionEntry(
        run_id=run_id,
        position=0 if last is None else last + 1,
        url=url[:_MAX_URL_LENGTH],
        title=title[:_MAX_TITLE_LENGTH] if title else None,
        verdict=BlogEntryVerdict.RETRY.value,
        post_id=post_id,
    )
    session.add(entry)
    session.flush()
    return entry


# --- Reading ---


def refreshable_source(session: Session, owner: User, source_id: uuid.UUID) -> BlogSource:
    """One of `owner`'s sources that a refresh may collect.

    Raises:
        BlogNotFoundError: If it is missing, archived or someone else's.
        SourcePausedError: If it is paused.
    """
    source = get_source(session, owner, source_id)
    if not source.enabled:
        raise SourcePausedError
    return source


def verdict_counts(
    session: Session, run_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, dict[str, int]]:
    """How many logged entries of each run got each verdict.

    Does not check ownership: callers pass runs they loaded for their owner.
    """
    if not run_ids:
        return {}
    stmt = (
        select(
            BlogCollectionEntry.run_id,
            BlogCollectionEntry.verdict,
            func.count(),
        )
        .where(BlogCollectionEntry.run_id.in_(run_ids))
        .group_by(BlogCollectionEntry.run_id, BlogCollectionEntry.verdict)
    )
    counts: dict[uuid.UUID, dict[str, int]] = {run_id: {} for run_id in run_ids}
    for run_id, verdict, count in session.execute(stmt).tuples():
        counts[run_id][verdict] = count
    return counts


def list_runs(
    session: Session, owner: User, source_id: uuid.UUID
) -> list[BlogCollectionRun]:
    """The runs of one of `owner`'s sources, newest first.

    Raises:
        BlogNotFoundError: If the source is missing, archived or someone else's.
    """
    source = get_source(session, owner, source_id)
    stmt = (
        select(BlogCollectionRun)
        .where(BlogCollectionRun.source_id == source.id)
        .order_by(BlogCollectionRun.started_at.desc(), BlogCollectionRun.id.desc())
    )
    return list(session.scalars(stmt))


def get_run(
    session: Session, owner: User, source_id: uuid.UUID, run_id: uuid.UUID
) -> BlogCollectionRun:
    """One run of one of `owner`'s sources, with its entries.

    Raises:
        BlogNotFoundError: If the source or the run is not the caller's.
    """
    source = get_source(session, owner, source_id)
    run = session.get(BlogCollectionRun, run_id)
    if run is None or run.source_id != source.id:
        raise BlogNotFoundError(str(run_id))
    return run
