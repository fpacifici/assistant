"""The job that collects posts and processes them.

`BlogPipeline.run` goes through the sources one at a time: it collects what is
new, analyzes every pending post, embeds the posts marked useful, and sweeps
the text files of deleted posts. A failure is logged (Sentry picks it up),
counted, and never stops the run.

Every source it reads gets a run in the collection log (`assistant.blogs.runs`):
each entry the source listed with its verdict, then what the analysis did. A
manual refresh is a run of one source that skips the conditional GET, so the
log shows everything the source lists.

No transaction stays open across a network or model call: each step reads what
it needs, works, then reloads the row to write, and gives up if the row is
gone, because the user may delete a source at any moment.

Only one run can exist at a time, see `advisory_lock`.
"""

from __future__ import annotations

import calendar
import logging
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, TypeGuard
from urllib.parse import urljoin, urlsplit, urlunsplit

from sqlalchemy import select, text

from assistant.blogs.analysis import MIN_TEXT_CHARS, PostToAnalyze
from assistant.blogs.chunking import PostInfo, chunk_post
from assistant.blogs.discovery import (
    SitemapEntry,
    parse_feed,
    parse_robots,
    parse_sitemap,
)
from assistant.blogs.exceptions import FetchError
from assistant.blogs.extraction import extract_page, html_to_text
from assistant.blogs.fetch import fetch
from assistant.blogs.identity import is_http_url, post_key
from assistant.blogs.runs import (
    LoggedEntry,
    close_interrupted_runs,
    entry_for_post,
    record_entries,
    start_run,
)
from assistant.blogs.store import replace_post_chunks
from assistant.models.schema import (
    BlogCollectionRun,
    BlogEmbedStatus,
    BlogEntryAnalysis,
    BlogEntryVerdict,
    BlogMatchLevel,
    BlogPost,
    BlogPostState,
    BlogPostStatus,
    BlogRunOutcome,
    BlogRunTrigger,
    BlogSource,
    BlogSourceKind,
    BlogTextSource,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator
    from contextlib import AbstractContextManager
    from urllib.robotparser import RobotFileParser

    from langchain_core.embeddings import Embeddings
    from sqlalchemy import Engine, Select
    from sqlalchemy.orm import Session

    from assistant.blogs.analysis import PostAnalysis, PostAnalyzer
    from assistant.blogs.fetch import FetchResult
    from assistant.blogs.text_store import TextStore

    type SessionFactory = Callable[[], AbstractContextManager[Session]]

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
REQUEST_DELAY_SECONDS = 0.5
MAX_CHILD_SITEMAPS = 20
ROBOTS_USER_AGENT = "AssistantBlogCollector"

_MAX_URL_LENGTH = 2048
_MAX_TITLE_LENGTH = 1024
_MAX_ETAG_LENGTH = 1024
_MAX_LAST_MODIFIED_LENGTH = 255
_HTTP_SERVER_ERROR = 500
# Arbitrary, but must not change: every process has to agree on it.
_ADVISORY_LOCK_KEY = 7_302_114_659


@contextmanager
def advisory_lock(engine: Engine) -> Iterator[bool]:
    """Hold the Postgres advisory lock of the job, if it is free.

    The lock belongs to a dedicated connection held for the whole run, so
    nothing keeps a transaction open meanwhile and a crash releases it.

    Yields:
        Whether the lock was acquired.
    """
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        acquired = bool(
            connection.scalar(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": _ADVISORY_LOCK_KEY}
            ),
        )
        try:
            yield acquired
        finally:
            if acquired:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:key)"), {"key": _ADVISORY_LOCK_KEY}
                )


@dataclass
class RunReport:
    """What a run did. `failures` counts anything that went wrong."""

    sources_checked: int = 0
    posts_collected: int = 0
    posts_analyzed: int = 0
    posts_too_short: int = 0
    posts_embedded: int = 0
    files_swept: int = 0
    failures: int = 0
    would_collect: list[tuple[str, str]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _SourceView:
    """What collecting a source needs, readable with no session open."""

    id: uuid.UUID
    title: str
    kind: str
    feed_url: str
    etag: str | None
    last_modified: str | None
    collect_since: datetime


@dataclass(frozen=True, slots=True)
class _Candidate:
    """A post found at a source and not stored yet.

    Attributes:
        key: Its `post_key`.
        url: Its URL.
        published_at: Its date, or `None` for a feed entry that has none, which
            counts as published when first seen.
        title: Its title, if known.
        text: Text to hold on to: the feed's, used if the page yields nothing.
        page_text: Text extracted from the page while looking for its date,
            which saves fetching the page again.
        skipped: A sitemap URL that must not be fetched again.
    """

    key: str
    url: str
    published_at: datetime | None = None
    title: str | None = None
    text: str | None = None
    page_text: str | None = None
    skipped: bool = False


@dataclass(slots=True)
class _Reading:
    """The outcome of reading a source.

    Attributes:
        candidates: Posts to store, within the cap.
        skipped: Sitemap URLs to remember, so they are not fetched again.
        etag: The validator of the response.
        last_modified: The validator of the response.
        left_out: Posts were left for the next run, so the validators must not
            be saved: the next run would get a 304 and never see them.
        entries: Everything the source listed, with the verdict on each, for
            the collection log.
        not_modified: The source answered 304.
        stored_ids: The posts the source lists that are stored already, by
            key, so their log entries link to them.
    """

    candidates: list[_Candidate] = field(default_factory=list)
    skipped: list[_Candidate] = field(default_factory=list)
    etag: str | None = None
    last_modified: str | None = None
    left_out: bool = False
    entries: list[LoggedEntry] = field(default_factory=list)
    not_modified: bool = False
    stored_ids: dict[str, uuid.UUID] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class _AnalysisLog:
    """What analyzing a post did, for the collection log."""

    outcome: BlogEntryAnalysis
    text_source: BlogTextSource | None = None
    text_chars: int | None = None
    error: str | None = None
    analysis: PostAnalysis | None = None


@dataclass(frozen=True, slots=True)
class _PostJob:
    """What analyzing a post needs, readable with no session open."""

    post_id: uuid.UUID
    source_id: uuid.UUID
    url: str
    title: str | None
    preferences: str | None


@dataclass(frozen=True, slots=True)
class _EmbedJob:
    """What embedding a post needs, readable with no session open."""

    info: PostInfo
    source_id: uuid.UUID
    owner_id: uuid.UUID


def _entry_date(entry: Any) -> datetime | None:  # noqa: ANN401
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    try:
        return datetime.fromtimestamp(calendar.timegm(parsed), UTC)
    except (ValueError, OverflowError):
        return None


def _entry_text(entry: Any) -> str | None:  # noqa: ANN401
    """The longest text a feed gives for an entry: `content:encoded` or summary."""
    fragments = [item.get("value", "") for item in entry.get("content", [])]
    fragments.append(entry.get("summary", ""))
    texts = [html_to_text(fragment) for fragment in fragments if fragment]
    return max(texts, key=len, default=None) or None


def _feed_candidates(
    parsed: Any,  # noqa: ANN401
    feed_url: str,
) -> tuple[list[_Candidate], list[LoggedEntry]]:
    """Turn feed entries into candidates.

    Returns:
        The candidates, and the entries that can't be posts: with no link,
        which can't be opened, or with one too long to store.
    """
    found: dict[str, _Candidate] = {}
    invalid: list[LoggedEntry] = []
    for entry in parsed.entries:
        guid = str(entry.get("id") or "") or None
        link = str(entry.get("link") or "")
        title = str(entry.get("title") or "").strip() or None
        if not link and guid and is_http_url(guid):
            link = guid
        if not link:
            invalid.append(
                LoggedEntry(url="", verdict=BlogEntryVerdict.INVALID, title=title)
            )
            continue
        url = urljoin(feed_url, link)
        if len(url) > _MAX_URL_LENGTH:
            invalid.append(
                LoggedEntry(url=url, verdict=BlogEntryVerdict.INVALID, title=title)
            )
            continue
        key = post_key(url, guid)
        found.setdefault(
            key,
            _Candidate(
                key=key,
                url=url,
                published_at=_entry_date(entry),
                title=title,
                text=_entry_text(entry),
            ),
        )
    return list(found.values()), invalid


def _logged(
    candidate: _Candidate,
    verdict: BlogEntryVerdict,
    *,
    published_at: datetime | None = None,
) -> LoggedEntry:
    return LoggedEntry(
        url=candidate.url,
        verdict=verdict,
        title=candidate.title,
        published_at=candidate.published_at or published_at,
        feed_text_chars=len(candidate.text) if candidate.text else None,
        key=candidate.key,
    )


def _error_message(exc: Exception) -> str:
    """What the log says about a failure: never anything from a response."""
    if isinstance(exc, FetchError):
        return str(exc)
    return f"Could not analyze ({type(exc).__name__})"


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def _oldest_first(candidate: _Candidate) -> datetime:
    return candidate.published_at or datetime.now(UTC)


class BlogPipeline:
    """Collects and processes the posts of every enabled source."""

    def __init__(  # noqa: PLR0913
        self,
        session_factory: SessionFactory,
        analyzer: PostAnalyzer | None,
        embeddings: Embeddings | None,
        text_store: TextStore,
        *,
        max_posts_per_run: int,
        request_delay_seconds: float = REQUEST_DELAY_SECONDS,
    ) -> None:
        """Create a pipeline.

        Args:
            session_factory: Opens database sessions.
            analyzer: The model. Only a dry run can go without it.
            embeddings: The embedding model. Likewise.
            text_store: Where post text is saved.
            max_posts_per_run: Most posts collected per source per run.
            request_delay_seconds: Pause before every request after the first.
        """
        self._sessions = session_factory
        self._analyzer = analyzer
        self._embeddings = embeddings
        self._text_store = text_store
        self._max_posts = max_posts_per_run
        self._delay = request_delay_seconds
        self._requests_made = 0
        # Feed text waits here for the analysis in the same run.
        self._feed_text: dict[uuid.UUID, str] = {}
        # This run's entry in the collection log, by source.
        self._runs: dict[uuid.UUID, uuid.UUID] = {}

    def run(
        self,
        *,
        user_id: uuid.UUID | None = None,
        source_id: uuid.UUID | None = None,
        dry_run: bool = False,
        refresh_run_id: uuid.UUID | None = None,
    ) -> RunReport:
        """Run the job. The caller holds `advisory_lock`.

        Args:
            user_id: Only this user's sources.
            source_id: Only this source.
            dry_run: Fetch and report what would be collected, and do nothing
                else: no writes, no model calls and no log.
            refresh_run_id: A manual refresh of `source_id`, logged in this
                run, which the caller created. The source is read without a
                conditional GET, and there is no sweep.

        Returns:
            What happened.
        """
        if refresh_run_id is not None and source_id is None:
            msg = "A refresh is of one source"
            raise ValueError(msg)
        report = RunReport()
        if not dry_run:
            self._close_interrupted(refresh_run_id)
        if refresh_run_id is not None:
            assert source_id is not None
            self._runs[source_id] = refresh_run_id
        try:
            views = self._views(user_id, source_id, refresh=refresh_run_id is not None)
            for view in views:
                self._collect_source(view, report, dry_run=dry_run)
            if dry_run:
                return report
            self._analyze_pending(user_id, source_id, report)
            self._embed_pending(user_id, source_id, report)
        finally:
            if not dry_run:
                self._finish_runs()
        if refresh_run_id is None:
            self._sweep(report)
        return report

    def _close_interrupted(self, refresh_run_id: uuid.UUID | None) -> None:
        with self._sessions() as session:
            close_interrupted_runs(
                session, keep=[refresh_run_id] if refresh_run_id else []
            )
            session.commit()

    def _finish_runs(self) -> None:
        if not self._runs:
            return
        with self._sessions() as session:
            for run_id in self._runs.values():
                run = session.get(BlogCollectionRun, run_id)
                if run is not None and run.finished_at is None:
                    run.finished_at = datetime.now(UTC)
            session.commit()

    def _fetch(
        self,
        url: str,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> FetchResult:
        """Fetch politely: one request at a time, with a pause between them."""
        if self._requests_made and self._delay > 0:
            time.sleep(self._delay)
        self._requests_made += 1
        return fetch(url, etag=etag, last_modified=last_modified)

    # --- Collect ---

    def _views(
        self,
        user_id: uuid.UUID | None,
        source_id: uuid.UUID | None,
        *,
        refresh: bool = False,
    ) -> list[_SourceView]:
        stmt = (
            select(BlogSource)
            .where(BlogSource.enabled.is_(True), BlogSource.archived_at.is_(None))
            .order_by(BlogSource.created_at, BlogSource.id)
        )
        with self._sessions() as session:
            sources = session.scalars(_scoped(stmt, user_id, source_id))
            return [
                _SourceView(
                    id=source.id,
                    title=source.title,
                    kind=source.kind,
                    feed_url=source.feed_url,
                    # A refresh wants to see everything the source lists.
                    etag=None if refresh else source.etag,
                    last_modified=None if refresh else source.last_modified,
                    collect_since=source.collect_since,
                )
                for source in sources
            ]

    def _collect_source(
        self, view: _SourceView, report: RunReport, *, dry_run: bool
    ) -> None:
        report.sources_checked += 1
        if not dry_run and view.id not in self._runs:
            self._runs[view.id] = self._start_run(view)
        try:
            reading = self._read_source(view)
        except Exception as exc:
            report.failures += 1
            logger.exception("Could not collect source %s", view.id)
            if not dry_run:
                message = str(exc) if isinstance(exc, FetchError) else None
                self._record_failure(view, message or "Could not read this source")
            return
        if dry_run:
            report.would_collect.extend(
                (view.title, candidate.url) for candidate in reading.candidates
            )
            return
        self._store_reading(view, reading, report)

    def _start_run(self, view: _SourceView) -> uuid.UUID:
        with self._sessions() as session:
            run = start_run(session, view.id, BlogRunTrigger.JOB)
            session.commit()
            return run.id

    def _read_source(self, view: _SourceView) -> _Reading:
        result = self._fetch(
            view.feed_url, etag=view.etag, last_modified=view.last_modified
        )
        result.raise_for_status()
        if result.not_modified:
            return _Reading(
                etag=view.etag, last_modified=view.last_modified, not_modified=True
            )
        if view.kind == BlogSourceKind.SITEMAP.value:
            reading = self._read_sitemap(view, result)
        else:
            reading = self._read_feed(view, result)
        reading.etag = result.etag
        reading.last_modified = result.last_modified
        return reading

    def _stored(self, view: _SourceView, keys: list[str]) -> dict[str, uuid.UUID]:
        """The posts stored already, by key: they never reach the model again."""
        if not keys:
            return {}
        with self._sessions() as session:
            rows = session.execute(
                select(BlogPost.post_key, BlogPost.id).where(
                    BlogPost.source_id == view.id,
                    BlogPost.post_key.in_(keys),
                ),
            )
            return dict(rows.tuples().all())

    def _capped(self, candidates: list[_Candidate]) -> tuple[list[_Candidate], bool]:
        """The oldest candidates that fit a run, and whether any did not."""
        ordered = sorted(candidates, key=_oldest_first)
        return ordered[: self._max_posts], len(ordered) > self._max_posts

    def _read_feed(self, view: _SourceView, result: FetchResult) -> _Reading:
        parsed = parse_feed(result.content)
        if parsed is None:
            msg = "The feed could not be read"
            raise FetchError(msg)
        candidates, invalid = _feed_candidates(parsed, view.feed_url)
        stored = self._stored(view, [c.key for c in candidates])
        verdicts: dict[str, BlogEntryVerdict] = {}
        fresh: list[_Candidate] = []
        for candidate in candidates:
            if candidate.key in stored:
                verdicts[candidate.key] = BlogEntryVerdict.STORED
            elif (
                candidate.published_at is not None
                and candidate.published_at < view.collect_since
            ):
                verdicts[candidate.key] = BlogEntryVerdict.TOO_OLD
            else:
                fresh.append(candidate)
        chosen, left_out = self._capped(fresh)
        for candidate in fresh:
            verdicts[candidate.key] = BlogEntryVerdict.OVER_CAP
        for candidate in chosen:
            verdicts[candidate.key] = BlogEntryVerdict.NEW
        entries = [_logged(c, verdicts[c.key]) for c in candidates]
        return _Reading(
            candidates=chosen,
            left_out=left_out,
            entries=entries + invalid,
            stored_ids=stored,
        )

    def _sitemap_pages(
        self, view: _SourceView, result: FetchResult
    ) -> list[SitemapEntry]:
        sitemap = parse_sitemap(result.content)
        if sitemap is None:
            msg = "The sitemap could not be read"
            raise FetchError(msg)
        pages = list(sitemap.pages)
        children = [
            child
            for child in sitemap.children
            if child.lastmod is None or child.lastmod >= view.collect_since
        ]
        children.sort(key=lambda c: c.lastmod or view.collect_since, reverse=True)
        for child in children[:MAX_CHILD_SITEMAPS]:
            page = self._fetch(child.url)
            page.raise_for_status()
            nested = parse_sitemap(page.content)
            if nested is not None:
                pages.extend(nested.pages)
        return pages

    def _robots(self, url: str) -> RobotFileParser | None:
        """A site's robots rules, or `None` if it has none.

        Raises:
            FetchError: If they can't be read: we can't know what is allowed,
                so the source fails this run.
        """
        result = self._fetch(f"{_origin(url)}/robots.txt")
        if result.status >= _HTTP_SERVER_ERROR:
            result.raise_for_status()
        return parse_robots(result.content) if result.ok else None

    def _read_undated(
        self, view: _SourceView, candidate: _Candidate
    ) -> _Candidate | None:
        """Look for a sitemap page's date on the page itself.

        Returns:
            The candidate with its date and text, marked skipped when it has
            no date or is too old; `None` if the page can't be read now.
        """
        try:
            page = self._fetch(candidate.url)
            page.raise_for_status()
        except FetchError:
            logger.info("Could not read %s, will try again", candidate.url)
            return None
        extracted = extract_page(page.content, page.url)
        date = extracted.published_at
        return _Candidate(
            key=candidate.key,
            url=candidate.url,
            published_at=date,
            title=extracted.title,
            page_text=extracted.text,
            skipped=date is None or date < view.collect_since,
        )

    def _allowed_pages(
        self, view: _SourceView, result: FetchResult
    ) -> tuple[list[SitemapEntry], list[LoggedEntry]]:
        """The sitemap's pages we may collect, and those refused, for the log."""
        robots = self._robots(view.feed_url)
        allowed: list[SitemapEntry] = []
        refused: list[LoggedEntry] = []
        for entry in self._sitemap_pages(view, result):
            if len(entry.url) > _MAX_URL_LENGTH:
                refused.append(
                    LoggedEntry(url=entry.url, verdict=BlogEntryVerdict.INVALID)
                )
            elif robots is not None and not robots.can_fetch(
                ROBOTS_USER_AGENT, entry.url
            ):
                refused.append(
                    LoggedEntry(
                        url=entry.url,
                        verdict=BlogEntryVerdict.ROBOTS,
                        published_at=entry.lastmod,
                    ),
                )
            else:
                allowed.append(entry)
        return allowed, refused

    def _look_up_undated(
        self,
        view: _SourceView,
        undated: list[_Candidate],
        reading: _Reading,
        log: dict[str, LoggedEntry],
    ) -> list[_Candidate]:
        """Find the dates of undated pages on the pages themselves.

        Every undated URL costs a request, so they are capped too.

        Returns:
            The pages that turned out recent enough to collect.
        """
        reading.left_out = len(undated) > self._max_posts
        for candidate in undated[self._max_posts :]:
            log[candidate.key] = _logged(candidate, BlogEntryVerdict.OVER_CAP)
        dated: list[_Candidate] = []
        for candidate in undated[: self._max_posts]:
            found = self._read_undated(view, candidate)
            if found is None:
                reading.left_out = True
                log[candidate.key] = _logged(candidate, BlogEntryVerdict.UNREADABLE)
            elif found.skipped:
                reading.skipped.append(found)
                verdict = (
                    BlogEntryVerdict.NO_DATE
                    if found.published_at is None
                    else BlogEntryVerdict.TOO_OLD
                )
                log[candidate.key] = _logged(found, verdict)
            else:
                dated.append(found)
        return dated

    def _read_sitemap(self, view: _SourceView, result: FetchResult) -> _Reading:
        entries, refused = self._allowed_pages(view, result)
        lastmods = {post_key(entry.url): entry.lastmod for entry in entries}
        urls = {post_key(entry.url): entry.url for entry in entries}
        stored = self._stored(view, list(urls))
        # The log, by key, in the sitemap's order. What is not stored gets its
        # own verdict below.
        log = {
            key: LoggedEntry(
                url=url,
                verdict=BlogEntryVerdict.STORED,
                published_at=lastmods[key],
                key=key,
            )
            for key, url in urls.items()
        }

        dated: list[_Candidate] = []
        undated: list[_Candidate] = []
        for key, url in urls.items():
            lastmod = lastmods[key]
            if key in stored:
                continue
            if lastmod is None:
                undated.append(_Candidate(key=key, url=url))
            elif lastmod >= view.collect_since:
                dated.append(_Candidate(key, url, lastmod))
            else:
                log[key] = _logged(
                    _Candidate(key, url, lastmod), BlogEntryVerdict.TOO_OLD
                )

        reading = _Reading(stored_ids=stored)
        dated.extend(self._look_up_undated(view, undated, reading, log))
        reading.candidates, over_cap = self._capped(dated)
        reading.left_out = reading.left_out or over_cap
        for candidate in dated:
            log[candidate.key] = _logged(candidate, BlogEntryVerdict.OVER_CAP)
        for candidate in reading.candidates:
            log[candidate.key] = _logged(candidate, BlogEntryVerdict.NEW)
        reading.entries = [*log.values(), *refused]
        return reading

    def _run_of(self, session: Session, view: _SourceView) -> BlogCollectionRun | None:
        run_id = self._runs.get(view.id)
        return session.get(BlogCollectionRun, run_id) if run_id else None

    def _record_failure(self, view: _SourceView, message: str) -> None:
        with self._sessions() as session:
            source = session.get(BlogSource, view.id)
            if source is None:
                return
            source.last_fetched_at = datetime.now(UTC)
            source.last_error = message
            source.consecutive_failures += 1
            run = self._run_of(session, view)
            if run is not None:
                run.outcome = BlogRunOutcome.FAILED.value
                run.error = message
            session.commit()

    def _store_reading(
        self, view: _SourceView, reading: _Reading, report: RunReport
    ) -> None:
        with self._sessions() as session:
            source = session.get(BlogSource, view.id, with_for_update=True)
            if source is None or source.archived_at is not None or not source.enabled:
                return
            page_texts: dict[uuid.UUID, str] = {}
            post_ids = dict(reading.stored_ids)
            for candidate in reading.candidates:
                post = _new_post(view, candidate, BlogPostStatus.PENDING)
                session.add(post)
                post_ids[candidate.key] = post.id
                if candidate.text:
                    self._feed_text[post.id] = candidate.text
                if candidate.page_text:
                    page_texts[post.id] = candidate.page_text
            for candidate in reading.skipped:
                session.add(_new_post(view, candidate, BlogPostStatus.SKIPPED))
            if not reading.left_out:
                source.etag = _bounded(reading.etag, _MAX_ETAG_LENGTH)
                source.last_modified = _bounded(
                    reading.last_modified, _MAX_LAST_MODIFIED_LENGTH
                )
            source.last_fetched_at = datetime.now(UTC)
            source.last_error = None
            source.consecutive_failures = 0
            run = self._run_of(session, view)
            if run is not None:
                session.flush()  # the posts, before entries point at them
                run.outcome = (
                    BlogRunOutcome.NOT_MODIFIED
                    if reading.not_modified
                    else BlogRunOutcome.COLLECTED
                ).value
                record_entries(session, run, reading.entries, post_ids)
            session.commit()
        for post_id, page_text in page_texts.items():
            self._text_store.write(post_id, page_text)
        report.posts_collected += len(reading.candidates)

    # --- Analyze ---

    def _analyze_pending(
        self,
        user_id: uuid.UUID | None,
        source_id: uuid.UUID | None,
        report: RunReport,
    ) -> None:
        stmt = (
            select(BlogPost.id)
            .join(BlogSource, BlogSource.id == BlogPost.source_id)
            .where(BlogPost.status == BlogPostStatus.PENDING.value)
            .order_by(BlogPost.published_at, BlogPost.id)
        )
        with self._sessions() as session:
            post_ids = list(session.scalars(_scoped(stmt, user_id, source_id)))
        for post_id in post_ids:
            self._analyze_post(post_id, report)

    def _analyze_post(self, post_id: uuid.UUID, report: RunReport) -> None:
        job = self._load_job(post_id)
        if job is None:
            return
        text_source: BlogTextSource | None = None
        text_chars: int | None = None
        try:
            post_text, text_source = self._post_text(job)
            text_chars = len(post_text)
            if len(post_text.strip()) < MIN_TEXT_CHARS:
                self._fail_too_short(job, report)
                self._log_analysis(
                    job,
                    _AnalysisLog(BlogEntryAnalysis.TOO_SHORT, text_source, text_chars),
                )
                return
            analysis = self._analyze_text(job, post_text)
        except Exception as exc:
            report.failures += 1
            logger.exception("Could not analyze post %s", job.post_id)
            gave_up = self._record_attempt(job)
            outcome = BlogEntryAnalysis.FAILED if gave_up else BlogEntryAnalysis.ERROR
            self._log_analysis(
                job, _AnalysisLog(outcome, text_source, text_chars, _error_message(exc))
            )
            return
        self._store_analysis(job, analysis, report)
        self._log_analysis(
            job,
            _AnalysisLog(
                BlogEntryAnalysis.PROCESSED, text_source, text_chars, analysis=analysis
            ),
        )

    def _log_analysis(self, job: _PostJob, log: _AnalysisLog) -> None:
        """Write what the analysis did into this run's entry for the post.

        A post analyzed again, collected by an earlier run, gets an entry of
        its own. The log is for the user to troubleshoot: failing to write it
        never fails the post.
        """
        run_id = self._runs.get(job.source_id)
        if run_id is None:
            return
        try:
            with self._sessions() as session:
                entry = entry_for_post(
                    session, run_id, job.post_id, url=job.url, title=job.title
                )
                if entry is None:
                    return
                entry.analysis = log.outcome.value
                entry.text_source = log.text_source.value if log.text_source else None
                entry.text_chars = log.text_chars
                entry.error = log.error
                entry.analyzed_at = datetime.now(UTC)
                if log.analysis is not None:
                    entry.summary = log.analysis.summary.strip()
                    entry.match_level = (
                        BlogMatchLevel(log.analysis.match_level).value
                        if log.analysis.match_level
                        else None
                    )
                    entry.motivation = (log.analysis.motivation or "").strip() or None
                session.commit()
        except Exception:
            logger.exception("Could not log the analysis of post %s", job.post_id)

    def _load_job(self, post_id: uuid.UUID) -> _PostJob | None:
        with self._sessions() as session:
            post = session.get(BlogPost, post_id)
            if post is None or post.status != BlogPostStatus.PENDING.value:
                return None
            return _PostJob(
                post_id=post.id,
                source_id=post.source_id,
                url=post.url,
                title=post.title,
                preferences=post.source.preferences,
            )

    def _post_text(self, job: _PostJob) -> tuple[str, BlogTextSource]:
        """The post's text, from its file or else fetched and saved.

        The file is written before the model is called, so a retry needs no
        new fetch and keeps feed-only text.

        Returns:
            The text and where it came from.

        Raises:
            FetchError: If the page can't be read and the feed gave no text;
                the next run tries again.
        """
        stored = self._text_store.read(job.post_id)
        if stored is not None:
            return stored, BlogTextSource.FILE
        feed_text = self._feed_text.get(job.post_id, "")
        page_text = ""
        try:
            page = self._fetch(job.url)
            page.raise_for_status()
        except FetchError:
            if not feed_text:
                raise
            logger.info("Using feed text for %s", job.url)
        else:
            extracted = extract_page(page.content, page.url)
            page_text = extracted.text or ""
            if extracted.title and not job.title:
                self._store_page_title(job.post_id, extracted.title)
        # A teaser page or a paywall yields less than the feed did.
        use_page = len(page_text) >= MIN_TEXT_CHARS or len(page_text) >= len(feed_text)
        chosen = page_text if use_page else feed_text
        if chosen:
            self._text_store.write(job.post_id, chosen)
        return chosen, BlogTextSource.PAGE if use_page else BlogTextSource.FEED

    def _store_page_title(self, post_id: uuid.UUID, title: str) -> None:
        with self._sessions() as session:
            post = session.get(BlogPost, post_id)
            if post is not None and not post.title:
                post.title = title[:_MAX_TITLE_LENGTH]
                session.commit()

    def _analyze_text(self, job: _PostJob, post_text: str) -> PostAnalysis:
        if self._analyzer is None:
            msg = "AI is disabled"
            raise RuntimeError(msg)
        return self._analyzer.analyze(
            PostToAnalyze(
                post_id=job.post_id,
                source_id=job.source_id,
                title=job.title,
                text=post_text,
                preferences=job.preferences,
            ),
        )

    def _locked_pending(self, session: Session, post_id: uuid.UUID) -> BlogPost | None:
        post = session.get(BlogPost, post_id, with_for_update=True)
        if post is None or post.status != BlogPostStatus.PENDING.value:
            return None
        return post

    def _fail_too_short(self, job: _PostJob, report: RunReport) -> None:
        with self._sessions() as session:
            post = self._locked_pending(session, job.post_id)
            if post is not None:
                post.status = BlogPostStatus.FAILED.value
            session.commit()
        report.posts_too_short += 1
        logger.info("Post %s is too short to summarize", job.post_id)

    def _record_attempt(self, job: _PostJob) -> bool:
        """Count a failed attempt.

        Returns:
            Whether the post is out of attempts, and failed.
        """
        gave_up = False
        with self._sessions() as session:
            post = self._locked_pending(session, job.post_id)
            if post is not None:
                post.attempts += 1
                if post.attempts >= MAX_ATTEMPTS:
                    post.status = BlogPostStatus.FAILED.value
                    gave_up = True
            session.commit()
        return gave_up

    def _store_analysis(
        self, job: _PostJob, analysis: PostAnalysis, report: RunReport
    ) -> None:
        with self._sessions() as session:
            post = self._locked_pending(session, job.post_id)
            if post is not None:
                model_title = (analysis.title or "").strip() or None
                post.title = post.title or (
                    model_title[:_MAX_TITLE_LENGTH] if model_title else None
                )
                post.summary = analysis.summary.strip()
                post.match_level = (
                    BlogMatchLevel(analysis.match_level).value
                    if analysis.match_level
                    else None
                )
                post.motivation = (analysis.motivation or "").strip() or None
                post.status = BlogPostStatus.PROCESSED.value
                report.posts_analyzed += 1
            session.commit()

    # --- Embed ---

    def _embed_pending(
        self,
        user_id: uuid.UUID | None,
        source_id: uuid.UUID | None,
        report: RunReport,
    ) -> None:
        stmt = (
            select(BlogPost.id)
            .join(BlogSource, BlogSource.id == BlogPost.source_id)
            .where(BlogPost.embed_status == BlogEmbedStatus.PENDING.value)
            .order_by(BlogPost.evaluated_at, BlogPost.id)
        )
        with self._sessions() as session:
            post_ids = list(session.scalars(_scoped(stmt, user_id, source_id)))
        for post_id in post_ids:
            self._embed_post(post_id, report)

    def _embed_post(self, post_id: uuid.UUID, report: RunReport) -> None:
        job = self._load_embed_job(post_id)
        if job is None:
            return
        try:
            # Never fetches: with no file, title and summary are all there is.
            chunks = chunk_post(job.info, self._text_store.read(post_id) or "")
            if self._embeddings is None:
                msg = "AI is disabled"
                raise RuntimeError(msg)  # noqa: TRY301
            vectors = self._embeddings.embed_documents([c.text for c in chunks])
            with self._sessions() as session:
                post = session.get(BlogPost, post_id, with_for_update=True)
                # The verdict may have changed while OpenAI was answering, and
                # the user's choice wins.
                if _wants_embedding(post):
                    replace_post_chunks(
                        session,
                        post_id=post_id,
                        source_id=job.source_id,
                        owner_id=job.owner_id,
                        chunks=chunks,
                        embeddings=vectors,
                    )
                    post.embed_status = BlogEmbedStatus.DONE.value
                    report.posts_embedded += 1
                session.commit()
        except Exception:
            report.failures += 1
            logger.exception("Could not embed post %s", post_id)
            self._record_embed_attempt(post_id)

    def _load_embed_job(self, post_id: uuid.UUID) -> _EmbedJob | None:
        with self._sessions() as session:
            post = session.get(BlogPost, post_id)
            if post is None or not _wants_embedding(post):
                return None
            return _EmbedJob(
                info=PostInfo(
                    title=post.title or post.url,
                    source_title=post.source.title,
                    summary=post.summary,
                    url=post.url,
                    published_at=post.published_at,
                ),
                source_id=post.source_id,
                owner_id=post.source.owner_id,
            )

    def _record_embed_attempt(self, post_id: uuid.UUID) -> None:
        with self._sessions() as session:
            post = session.get(BlogPost, post_id, with_for_update=True)
            if post is not None and _wants_embedding(post):
                post.embed_attempts += 1
                if post.embed_attempts >= MAX_ATTEMPTS:
                    post.embed_status = BlogEmbedStatus.FAILED.value
            session.commit()

    # --- Sweep ---

    def _sweep(self, report: RunReport) -> None:
        def existing(post_ids: Iterable[uuid.UUID]) -> set[uuid.UUID]:
            with self._sessions() as session:
                stmt = select(BlogPost.id).where(BlogPost.id.in_(list(post_ids)))
                return set(session.scalars(stmt))

        try:
            report.files_swept = self._text_store.sweep(existing)
        except Exception:
            report.failures += 1
            logger.exception("Could not sweep post text files")


def _scoped[T: Select[Any]](
    stmt: T, user_id: uuid.UUID | None, source_id: uuid.UUID | None
) -> T:
    """Narrow a statement that has `BlogSource` in its FROM."""
    if user_id is not None:
        stmt = stmt.where(BlogSource.owner_id == user_id)
    if source_id is not None:
        stmt = stmt.where(BlogSource.id == source_id)
    return stmt


def _wants_embedding(post: BlogPost | None) -> TypeGuard[BlogPost]:
    return (
        post is not None
        and post.state == BlogPostState.USEFUL.value
        and post.embed_status == BlogEmbedStatus.PENDING.value
    )


def _bounded(value: str | None, limit: int) -> str | None:
    """A validator too long for its column is the same as no validator."""
    return value if value is None or len(value) <= limit else None


def _new_post(
    view: _SourceView, candidate: _Candidate, status: BlogPostStatus
) -> BlogPost:
    title = candidate.title[:_MAX_TITLE_LENGTH] if candidate.title else None
    return BlogPost(
        id=uuid.uuid4(),
        source_id=view.id,
        post_key=candidate.key,
        url=candidate.url,
        title=title,
        published_at=candidate.published_at or datetime.now(UTC),
        status=status.value,
    )
