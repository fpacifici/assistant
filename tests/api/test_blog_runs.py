"""Tests for the collection log and refresh endpoints (against Postgres)."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Generator, Iterator
from contextlib import AbstractContextManager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from assistant.api.app import create_app
from assistant.api.dependencies import get_session
from assistant.blogs import pipeline as pipeline_module
from assistant.blogs.pipeline import BlogPipeline, advisory_lock
from assistant.blogs.refresh import BlogRefresher
from assistant.blogs.text_store import TextStore
from assistant.models.schema import BlogSource, BlogSourceKind, User
from tests.api.conftest import make_auth_headers
from tests.blogs.fakes import FakeAnalyzer, FakeWeb

pytestmark = pytest.mark.postgres

SITE = "https://blog.example.com"
FEED = f"{SITE}/feed.xml"
LONG_TEXT = "Plenty of words to summarize here. " * 20
Headers = dict[str, str]


def _rss(*slugs: str) -> bytes:
    date = datetime.now(UTC).strftime("%a, %d %b %Y %H:%M:%S +0000")
    items = "".join(
        f"<item><link>{SITE}/{slug}</link><title>{slug}</title>"
        f"<pubDate>{date}</pubDate><description>{LONG_TEXT}</description></item>"
        for slug in slugs
    )
    return (
        f'<?xml version="1.0"?><rss version="2.0"><channel><title>Blog</title>'
        f"{items}</channel></rss>"
    ).encode()


@pytest.fixture
def owner(pg_session: Session) -> User:
    user = User(email="owner@example.com", firstname="O", lastname="W")
    pg_session.add(user)
    pg_session.flush()
    return user


@pytest.fixture
def headers(owner: User) -> Headers:
    return make_auth_headers(owner.uid)


@pytest.fixture
def source(pg_session: Session, owner: User) -> BlogSource:
    source = BlogSource(
        owner_id=owner.uid,
        url=SITE,
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
    web = FakeWeb(pages={FEED: _rss("one"), f"{SITE}/one": 404})
    with patch.object(pipeline_module, "fetch", web):
        yield web


@pytest.fixture
def client(
    pg_session: Session,
    pg_session_factory: Callable[[], AbstractContextManager[Session]],
    request: pytest.FixtureRequest,
    tmp_path: Path,
    web: FakeWeb,  # noqa: ARG001
) -> Iterator[TestClient]:
    """A client whose refreshes run at once, in the request."""
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

    refresher = BlogRefresher(
        pg_session_factory, lambda: advisory_lock(engine), pipeline, lambda work: work()
    )

    def override_get_session() -> Generator[Session]:
        yield pg_session

    app = create_app(blog_refresher=refresher)
    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app, raise_server_exceptions=True) as tc:
        yield tc


def _refresh(client: TestClient, headers: Headers, source: BlogSource) -> dict:
    response = client.post(f"/blog/source/{source.id}/refresh", headers=headers)
    assert response.status_code == 202, response.text
    return response.json()


# --- Refresh ---


def test_refresh_answers_with_its_run(
    client: TestClient, headers: Headers, source: BlogSource
) -> None:
    run = _refresh(client, headers, source)
    assert run["source_id"] == str(source.id)
    assert run["trigger"] == "manual"


def test_a_paused_source_cannot_be_refreshed(
    client: TestClient, pg_session: Session, headers: Headers, source: BlogSource
) -> None:
    source.enabled = False
    pg_session.flush()
    response = client.post(f"/blog/source/{source.id}/refresh", headers=headers)
    assert response.status_code == 409
    assert response.json()["detail"] == "Resume this blog to refresh it"


def test_refresh_waits_for_the_job(
    client: TestClient,
    headers: Headers,
    source: BlogSource,
    request: pytest.FixtureRequest,
) -> None:
    engine: Engine = request.getfixturevalue("_pg_engine")
    with advisory_lock(engine):
        response = client.post(f"/blog/source/{source.id}/refresh", headers=headers)
    assert response.status_code == 409
    assert "already running" in response.json()["detail"]


def test_refresh_needs_ai(
    pg_client: TestClient, headers: Headers, source: BlogSource
) -> None:
    response = pg_client.post(f"/blog/source/{source.id}/refresh", headers=headers)
    assert response.status_code == 503


# --- Log ---


def test_the_log_lists_runs_newest_first_with_counts(
    client: TestClient, headers: Headers, source: BlogSource, web: FakeWeb
) -> None:
    first = _refresh(client, headers, source)
    web.pages[FEED] = _rss("one", "two")
    web.pages[f"{SITE}/two"] = 404
    second = _refresh(client, headers, source)

    response = client.get(f"/blog/source/{source.id}/run", headers=headers)
    assert response.status_code == 200
    runs = response.json()
    assert [run["id"] for run in runs] == [second["id"], first["id"]]
    assert runs[0]["verdicts"] == {"stored": 1, "new": 1}
    assert runs[0]["outcome"] == "collected"
    assert runs[0]["finished_at"] is not None
    assert runs[0]["entries_found"] == 2


def test_a_run_shows_each_entry_and_what_the_model_did(
    client: TestClient, headers: Headers, source: BlogSource
) -> None:
    run = _refresh(client, headers, source)
    response = client.get(f"/blog/source/{source.id}/run/{run['id']}", headers=headers)
    assert response.status_code == 200
    [entry] = response.json()["entries"]
    assert entry["url"] == f"{SITE}/one"
    assert entry["verdict"] == "new"
    assert entry["post_id"] is not None
    assert entry["analysis"] == "processed"
    assert entry["text_source"] == "feed"
    assert entry["summary"] == "A summary."


def test_someone_elses_log_is_not_found(
    client: TestClient,
    pg_session: Session,
    headers: Headers,
    source: BlogSource,
) -> None:
    run = _refresh(client, headers, source)
    stranger = User(email="s@example.com", firstname="S", lastname="T")
    pg_session.add(stranger)
    pg_session.flush()
    other = make_auth_headers(stranger.uid)
    for response in (
        client.get(f"/blog/source/{source.id}/run", headers=other),
        client.get(f"/blog/source/{source.id}/run/{run['id']}", headers=other),
        client.post(f"/blog/source/{source.id}/refresh", headers=other),
    ):
        assert response.status_code == 404


def test_a_run_of_another_source_is_not_found(
    client: TestClient,
    pg_session: Session,
    owner: User,
    headers: Headers,
    source: BlogSource,
) -> None:
    run = _refresh(client, headers, source)
    other = BlogSource(
        owner_id=owner.uid,
        url=SITE,
        feed_url=f"{SITE}/other.xml",
        kind=BlogSourceKind.FEED.value,
        title="Other",
        collect_since=datetime.now(UTC),
    )
    pg_session.add(other)
    pg_session.flush()
    response = client.get(f"/blog/source/{other.id}/run/{run['id']}", headers=headers)
    assert response.status_code == 404
    missing = client.get(f"/blog/source/{source.id}/run/{uuid.uuid4()}", headers=headers)
    assert missing.status_code == 404


def test_the_log_needs_authentication(client: TestClient, source: BlogSource) -> None:
    assert client.get(f"/blog/source/{source.id}/run").status_code == 401
