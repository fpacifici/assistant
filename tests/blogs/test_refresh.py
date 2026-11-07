"""Tests for the manual refresh, on Postgres, with the web and the model faked."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from assistant.blogs import pipeline as pipeline_module
from assistant.blogs.exceptions import CollectionBusyError
from assistant.blogs.pipeline import BlogPipeline, advisory_lock
from assistant.blogs.refresh import BlogRefresher
from assistant.blogs.runs import start_run
from assistant.blogs.text_store import TextStore
from assistant.models.schema import (
    BlogCollectionRun,
    BlogRunTrigger,
    BlogSource,
    BlogSourceKind,
    User,
)
from tests.blogs.fakes import FakeAnalyzer, FakeWeb

pytestmark = pytest.mark.postgres

FEED = "https://blog.example.com/feed.xml"
_EMPTY_FEED = (
    b'<?xml version="1.0"?><rss version="2.0"><channel><title>Blog</title>'
    b"</channel></rss>"
)

type Work = Callable[[], None]


@pytest.fixture
def source(pg_session: Session) -> BlogSource:
    owner = User(email=f"{uuid.uuid4()}@example.com", firstname="A", lastname="B")
    pg_session.add(owner)
    pg_session.flush()
    source = BlogSource(
        owner_id=owner.uid,
        url="https://blog.example.com",
        feed_url=FEED,
        kind=BlogSourceKind.FEED.value,
        title="Blog",
        collect_since=datetime.now(UTC) - timedelta(days=7),
    )
    pg_session.add(source)
    pg_session.flush()
    return source


@pytest.fixture
def web() -> Iterator[FakeWeb]:
    web = FakeWeb(pages={FEED: _EMPTY_FEED})
    with patch.object(pipeline_module, "fetch", web):
        yield web


@pytest.fixture
def pending() -> list[Work]:
    """Work handed to the executor, run by the test when it chooses.

    Each piece holds the advisory lock until it runs, so a test must run all
    of it or the lock leaks into the next tests.
    """
    return []


@pytest.fixture
def refresher(
    pg_session_factory: Callable[[], AbstractContextManager[Session]],
    request: pytest.FixtureRequest,
    tmp_path: Path,
    pending: list[Work],
    web: FakeWeb,  # noqa: ARG001
) -> BlogRefresher:
    engine: Engine = request.getfixturevalue("_pg_engine")

    def pipeline() -> BlogPipeline:
        return BlogPipeline(
            pg_session_factory,
            FakeAnalyzer(),  # type: ignore[arg-type]
            None,
            TextStore(tmp_path),
            max_posts_per_run=50,
            request_delay_seconds=0,
        )

    return BlogRefresher(
        pg_session_factory, lambda: advisory_lock(engine), pipeline, pending.append
    )


def _lock_is_free(request: pytest.FixtureRequest) -> bool:
    engine: Engine = request.getfixturevalue("_pg_engine")
    with advisory_lock(engine) as acquired:
        return acquired


# --- Refresh ---


def test_a_refresh_creates_its_run_then_works_in_the_background(  # noqa: PLR0913
    refresher: BlogRefresher,
    source: BlogSource,
    pg_session: Session,
    pending: list[Work],
    web: FakeWeb,
    request: pytest.FixtureRequest,
) -> None:
    run_id = refresher.start(source.id)

    run = pg_session.get(BlogCollectionRun, run_id)
    assert run is not None
    assert run.trigger == "manual"
    assert run.finished_at is None
    assert web.requested == []
    assert not _lock_is_free(request)

    [work] = pending
    work()

    pg_session.refresh(run)
    assert run.outcome == "collected"
    assert run.finished_at is not None
    assert web.requested == [FEED]
    assert _lock_is_free(request)


def test_a_refresh_waits_for_the_job(
    refresher: BlogRefresher,
    source: BlogSource,
    pg_session: Session,
    pending: list[Work],
    request: pytest.FixtureRequest,
) -> None:
    engine: Engine = request.getfixturevalue("_pg_engine")
    with advisory_lock(engine) as acquired:
        assert acquired
        with pytest.raises(CollectionBusyError):
            refresher.start(source.id)
    assert pending == []
    stmt = select(BlogCollectionRun).where(BlogCollectionRun.source_id == source.id)
    assert list(pg_session.scalars(stmt)) == []


def test_a_crashing_refresh_releases_the_lock(
    refresher: BlogRefresher,
    source: BlogSource,
    pending: list[Work],
    request: pytest.FixtureRequest,
) -> None:
    refresher.start(source.id)
    with patch.object(BlogPipeline, "run", side_effect=RuntimeError("boom")):
        pending[0]()
    assert _lock_is_free(request)


def test_a_refresh_closes_an_interrupted_one(
    refresher: BlogRefresher,
    source: BlogSource,
    pg_session: Session,
    pending: list[Work],
) -> None:
    dead = start_run(pg_session, source.id, BlogRunTrigger.MANUAL)
    pg_session.flush()

    current = refresher.start(source.id)

    pg_session.refresh(dead)
    assert dead.interrupted
    assert dead.finished_at is not None
    run = pg_session.get(BlogCollectionRun, current)
    assert run is not None
    assert not run.interrupted
    pending[0]()  # releases the lock
