"""Tests for the job, on Postgres, with the web and the model faked."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from assistant.blogs import pipeline as pipeline_module
from assistant.blogs.analysis import MIN_TEXT_CHARS, PostAnalysis
from assistant.blogs.exceptions import FetchError
from assistant.blogs.identity import post_key
from assistant.blogs.pipeline import (
    MAX_ATTEMPTS,
    BlogPipeline,
    RunReport,
    advisory_lock,
)
from assistant.blogs.service import set_post_state
from assistant.blogs.store import post_chunk_embedding
from assistant.blogs.text_store import TextStore
from assistant.models.schema import (
    BlogEmbedStatus,
    BlogPost,
    BlogPostState,
    BlogPostStatus,
    BlogSource,
    BlogSourceKind,
    User,
)
from assistant.vectors.store import EMBEDDING_DIMENSIONS
from tests.blogs.fakes import FakeAnalyzer, FakeWeb

pytestmark = pytest.mark.postgres

SITE = "https://blog.example.com"
FEED = f"{SITE}/feed.xml"
SITEMAP = f"{SITE}/sitemap.xml"
ROBOTS = f"{SITE}/robots.txt"
LONG_TEXT = "Plenty of words to summarize here. " * 20
NOW = datetime.now(UTC)
RFC822 = "%a, %d %b %Y %H:%M:%S +0000"


def _item(
    slug: str,
    *,
    date: datetime | None = NOW,
    title: str | None = None,
    guid: str | None = None,
    body: str = LONG_TEXT,
) -> str:
    parts = [f"<link>{SITE}/{slug}</link>", f"<description>{body}</description>"]
    if title is not None:
        parts.append(f"<title>{title}</title>")
    if date is not None:
        parts.append(f"<pubDate>{date.strftime(RFC822)}</pubDate>")
    if guid is not None:
        parts.append(f'<guid isPermaLink="false">{guid}</guid>')
    return f"<item>{''.join(parts)}</item>"


def _rss(*items: str) -> bytes:
    body = "".join(items)
    return (
        f'<?xml version="1.0"?><rss version="2.0"><channel><title>Blog</title>'
        f"{body}</channel></rss>"
    ).encode()


def _page(title: str = "Page title", published: str | None = None) -> bytes:
    meta = (
        f'<meta property="article:published_time" content="{published}">'
        if published
        else ""
    )
    return (
        f"<html><head><title>{title}</title>{meta}</head><body><article><h1>{title}"
        f"</h1><p>{LONG_TEXT}</p></article></body></html>"
    ).encode()


def _sitemap(*urls: tuple[str, datetime | None]) -> bytes:
    entries = ""
    for url, lastmod in urls:
        date = f"<lastmod>{lastmod.isoformat()}</lastmod>" if lastmod else ""
        entries += f"<url><loc>{url}</loc>{date}</url>"
    return (
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{entries}</urlset>'
    ).encode()


@dataclass
class Job:
    """Everything a test needs to run the pipeline."""

    session: Session
    owner: User
    web: FakeWeb
    analyzer: FakeAnalyzer
    store: TextStore
    factory: Callable[[], AbstractContextManager[Session]]
    embeddings: DeterministicFakeEmbedding

    def source(self, **fields: object) -> BlogSource:
        values: dict[str, object] = {
            "owner_id": self.owner.uid,
            "url": SITE,
            "feed_url": FEED,
            "kind": BlogSourceKind.FEED.value,
            "title": "Blog",
            "collect_since": NOW - timedelta(days=7),
            **fields,
        }
        source = BlogSource(**values)
        self.session.add(source)
        self.session.flush()
        return source

    def run(self, *, max_posts: int = 50, **kwargs: object) -> RunReport:
        pipeline = BlogPipeline(
            self.factory,
            self.analyzer,  # type: ignore[arg-type]
            self.embeddings,
            self.store,
            max_posts_per_run=max_posts,
            request_delay_seconds=0,
        )
        return pipeline.run(**kwargs)  # type: ignore[arg-type]

    def posts(self, source: BlogSource) -> list[BlogPost]:
        self.session.expire_all()
        stmt = (
            select(BlogPost)
            .where(BlogPost.source_id == source.id)
            .order_by(BlogPost.published_at, BlogPost.url)
        )
        return list(self.session.scalars(stmt))


@pytest.fixture
def job(
    pg_session: Session,
    pg_session_factory: Callable[[], AbstractContextManager[Session]],
    tmp_path: Path,
) -> Iterator[Job]:
    owner = User(email=f"{uuid.uuid4()}@example.com", firstname="A", lastname="B")
    pg_session.add(owner)
    pg_session.flush()
    web = FakeWeb()
    with patch.object(pipeline_module, "fetch", web):
        yield Job(
            pg_session,
            owner,
            web,
            FakeAnalyzer(),
            TextStore(tmp_path),
            pg_session_factory,
            DeterministicFakeEmbedding(size=EMBEDDING_DIMENSIONS),
        )


# --- Collecting ---


def test_collects_and_analyzes_a_feed(job: Job) -> None:
    source = job.source()
    job.web.pages[FEED] = _rss(_item("one", title="One"))
    job.web.pages[f"{SITE}/one"] = _page()

    report = job.run()

    [post] = job.posts(source)
    assert post.title == "One"
    assert post.url == f"{SITE}/one"
    assert post.post_key == post_key(f"{SITE}/one")
    assert post.status == BlogPostStatus.PROCESSED.value
    assert post.state == BlogPostState.NEW.value
    assert post.summary == "A summary."
    assert report.posts_collected == 1
    assert report.posts_analyzed == 1
    assert report.failures == 0
    assert source.last_fetched_at is not None


def test_stored_posts_are_dropped(job: Job) -> None:
    source = job.source()
    job.web.pages[FEED] = _rss(_item("one", title="One"))
    job.web.pages[f"{SITE}/one"] = _page()
    job.run()

    job.web.pages[FEED] = _rss(_item("one", title="Edited title"), _item("two"))
    job.web.pages[f"{SITE}/two"] = _page()
    job.analyzer.calls.clear()
    job.run()

    posts = job.posts(source)
    assert len(posts) == 2
    assert {post.title for post in posts} == {"One", "Page title"}
    assert len(job.analyzer.calls) == 1


def test_a_domain_move_does_not_duplicate(job: Job) -> None:
    source = job.source()
    job.web.pages[FEED] = _rss(_item("one"))
    job.web.pages[f"{SITE}/one"] = _page()
    job.run()
    job.web.pages[FEED] = _rss(_item("one")).replace(
        SITE.encode(), b"https://moved.example.org"
    )
    job.run()
    assert len(job.posts(source)) == 1


def test_guid_identifies_a_post(job: Job) -> None:
    source = job.source()
    job.web.pages[FEED] = _rss(_item("one", guid="tag:x,1"))
    job.web.pages[f"{SITE}/one"] = _page()
    job.run()
    job.web.pages[FEED] = _rss(_item("renamed", guid="tag:x,1"))
    job.run()
    assert [post.url for post in job.posts(source)] == [f"{SITE}/one"]


def test_posts_before_collection_start_are_dropped(job: Job) -> None:
    source = job.source(collect_since=NOW - timedelta(days=1))
    job.web.pages[FEED] = _rss(
        _item("old", date=NOW - timedelta(days=2)),
        _item("recent", date=NOW - timedelta(hours=1)),
    )
    job.web.pages[f"{SITE}/recent"] = _page()
    job.run()
    assert [post.url for post in job.posts(source)] == [f"{SITE}/recent"]


def test_a_dateless_feed_entry_counts_as_published_when_first_seen(job: Job) -> None:
    source = job.source()
    job.web.pages[FEED] = _rss(_item("undated", date=None))
    job.web.pages[f"{SITE}/undated"] = _page()
    before = datetime.now(UTC)
    job.run()
    [post] = job.posts(source)
    assert post.published_at >= before.replace(microsecond=0)


def test_an_entry_with_no_link_is_ignored(job: Job) -> None:
    source = job.source()
    job.web.pages[FEED] = _rss(
        '<item><title>Nowhere</title><guid isPermaLink="false">x</guid></item>'
    )
    job.run()
    assert job.posts(source) == []


def test_paused_and_archived_sources_are_not_collected(job: Job) -> None:
    job.source(enabled=False)
    job.source(feed_url=f"{SITE}/other", archived_at=NOW)
    job.run()
    assert job.web.requested == []


def test_only_the_chosen_source_and_user(job: Job) -> None:
    source = job.source()
    job.source(feed_url=f"{SITE}/other.xml")
    job.web.pages[FEED] = _rss()
    job.run(source_id=source.id)
    assert job.web.requested == [FEED]
    job.web.requested.clear()
    job.run(user_id=uuid.uuid4())
    assert job.web.requested == []


# --- The run cap and conditional GET ---


def test_the_cap_takes_the_oldest_first(job: Job) -> None:
    source = job.source()
    job.web.etags[FEED] = '"v1"'
    job.web.pages[FEED] = _rss(
        _item("newest", date=NOW),
        _item("oldest", date=NOW - timedelta(days=3)),
        _item("middle", date=NOW - timedelta(days=2)),
    )
    for slug in ("newest", "oldest", "middle"):
        job.web.pages[f"{SITE}/{slug}"] = _page()

    job.run(max_posts=2)

    assert [post.url for post in job.posts(source)] == [
        f"{SITE}/oldest",
        f"{SITE}/middle",
    ]


def test_validators_are_not_saved_while_posts_wait(job: Job) -> None:
    source = job.source()
    job.web.etags[FEED] = '"v1"'
    job.web.pages[FEED] = _rss(
        _item("a", date=NOW - timedelta(days=1)), _item("b", date=NOW)
    )
    job.web.pages[f"{SITE}/a"] = _page()
    job.web.pages[f"{SITE}/b"] = _page()

    job.run(max_posts=1)
    assert source.etag is None

    job.web.requested.clear()
    job.run(max_posts=1)
    assert job.web.conditional[job.web.requested.index(FEED)] is None
    assert len(job.posts(source)) == 2
    job.session.refresh(source)
    assert source.etag == '"v1"'


def test_not_modified_collects_nothing(job: Job) -> None:
    source = job.source(etag='"v1"', consecutive_failures=2, last_error="old")
    job.web.pages[FEED] = 304
    report = job.run()
    assert job.web.conditional == ['"v1"']
    assert report.posts_collected == 0
    assert source.consecutive_failures == 0
    assert source.last_error is None
    assert source.etag == '"v1"'


# --- Sitemaps ---


def test_sitemap_uses_lastmod(job: Job) -> None:
    source = job.source(kind=BlogSourceKind.SITEMAP.value, feed_url=SITEMAP)
    job.web.pages[SITEMAP] = _sitemap(
        (f"{SITE}/new", NOW - timedelta(days=1)),
        (f"{SITE}/old", NOW - timedelta(days=30)),
    )
    job.web.pages[f"{SITE}/new"] = _page()
    job.run()
    [post] = job.posts(source)
    assert post.url == f"{SITE}/new"
    assert post.published_at == NOW - timedelta(days=1)
    assert f"{SITE}/old" not in job.web.requested


def test_sitemap_date_found_on_the_page(job: Job) -> None:
    source = job.source(kind=BlogSourceKind.SITEMAP.value, feed_url=SITEMAP)
    today = NOW.date().isoformat()
    job.web.pages[SITEMAP] = _sitemap((f"{SITE}/undated", None))
    job.web.pages[f"{SITE}/undated"] = _page(published=f"{today}T08:00:00+00:00")
    job.run()
    [post] = job.posts(source)
    assert post.status == BlogPostStatus.PROCESSED.value
    assert post.title == "Page title"
    assert job.web.requested.count(f"{SITE}/undated") == 1


def test_a_dateless_sitemap_post_is_skipped_and_never_fetched_again(job: Job) -> None:
    source = job.source(kind=BlogSourceKind.SITEMAP.value, feed_url=SITEMAP)
    job.web.pages[SITEMAP] = _sitemap((f"{SITE}/undated", None))
    job.web.pages[f"{SITE}/undated"] = _page()
    job.run()
    [post] = job.posts(source)
    assert post.status == BlogPostStatus.SKIPPED.value
    assert job.analyzer.calls == []

    job.web.requested.clear()
    job.run()
    assert f"{SITE}/undated" not in job.web.requested


def test_a_too_old_undated_sitemap_post_is_skipped(job: Job) -> None:
    source = job.source(kind=BlogSourceKind.SITEMAP.value, feed_url=SITEMAP)
    job.web.pages[SITEMAP] = _sitemap((f"{SITE}/ancient", None))
    job.web.pages[f"{SITE}/ancient"] = _page(published="2001-01-01T00:00:00+00:00")
    job.run()
    [post] = job.posts(source)
    assert post.status == BlogPostStatus.SKIPPED.value


def test_a_sitemap_page_that_fails_is_tried_again(job: Job) -> None:
    source = job.source(kind=BlogSourceKind.SITEMAP.value, feed_url=SITEMAP)
    job.web.etags[SITEMAP] = '"v1"'
    job.web.pages[SITEMAP] = _sitemap((f"{SITE}/flaky", None))
    job.web.pages[f"{SITE}/flaky"] = FetchError("down")
    job.run()
    assert job.posts(source) == []
    assert source.etag is None


def test_sitemap_respects_robots(job: Job) -> None:
    source = job.source(kind=BlogSourceKind.SITEMAP.value, feed_url=SITEMAP)
    job.web.pages[ROBOTS] = b"User-agent: *\nDisallow: /private/\n"
    job.web.pages[SITEMAP] = _sitemap((f"{SITE}/private/x", NOW), (f"{SITE}/public", NOW))
    job.web.pages[f"{SITE}/public"] = _page()
    job.run()
    assert [post.url for post in job.posts(source)] == [f"{SITE}/public"]
    assert f"{SITE}/private/x" not in job.web.requested


def test_empty_robots_allows_everything(job: Job) -> None:
    source = job.source(kind=BlogSourceKind.SITEMAP.value, feed_url=SITEMAP)
    job.web.pages[ROBOTS] = b""
    job.web.pages[SITEMAP] = _sitemap((f"{SITE}/public", NOW))
    job.web.pages[f"{SITE}/public"] = _page()
    job.run()
    assert len(job.posts(source)) == 1


def test_robots_that_cannot_be_read_fail_the_source(job: Job) -> None:
    source = job.source(kind=BlogSourceKind.SITEMAP.value, feed_url=SITEMAP)
    job.web.pages[ROBOTS] = 503
    job.web.pages[SITEMAP] = _sitemap((f"{SITE}/public", NOW))
    report = job.run()
    assert report.failures == 1
    assert job.posts(source) == []


def test_sitemap_index_is_followed_skipping_old_children(job: Job) -> None:
    source = job.source(kind=BlogSourceKind.SITEMAP.value, feed_url=SITEMAP)
    fresh, stale = f"{SITE}/fresh.xml", f"{SITE}/stale.xml"
    job.web.pages[SITEMAP] = (
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"<sitemap><loc>{fresh}</loc><lastmod>{NOW.isoformat()}</lastmod></sitemap>"
        f"<sitemap><loc>{stale}</loc><lastmod>2001-01-01</lastmod></sitemap>"
        "</sitemapindex>"
    ).encode()
    job.web.pages[fresh] = _sitemap((f"{SITE}/post", NOW))
    job.web.pages[f"{SITE}/post"] = _page()
    job.run()
    assert [post.url for post in job.posts(source)] == [f"{SITE}/post"]
    assert stale not in job.web.requested


def test_undated_sitemap_lookups_are_capped(job: Job) -> None:
    source = job.source(kind=BlogSourceKind.SITEMAP.value, feed_url=SITEMAP)
    job.web.etags[SITEMAP] = '"v1"'
    urls = [f"{SITE}/p{n}" for n in range(3)]
    job.web.pages[SITEMAP] = _sitemap(*((url, None) for url in urls))
    job.run(max_posts=1)
    assert sum(url in job.web.requested for url in urls) == 1
    assert source.etag is None


# --- Failures ---


def test_a_failing_source_does_not_stop_the_run(job: Job) -> None:
    failing = job.source(
        feed_url=f"{SITE}/broken.xml", created_at=NOW - timedelta(days=1)
    )
    working = job.source()
    job.web.pages[f"{SITE}/broken.xml"] = FetchError("Could not reach this URL")
    job.web.pages[FEED] = _rss(_item("one"))
    job.web.pages[f"{SITE}/one"] = _page()

    report = job.run()

    assert report.failures == 1
    assert failing.last_error == "Could not reach this URL"
    assert failing.consecutive_failures == 1
    assert failing.last_fetched_at is not None
    assert failing.enabled is True
    assert len(job.posts(working)) == 1


def test_http_error_is_recorded_without_content(job: Job) -> None:
    source = job.source()
    job.web.pages[FEED] = 500
    job.run()
    assert source.last_error == "The server answered HTTP 500"


def test_an_unexpected_error_gives_a_generic_message(job: Job) -> None:
    source = job.source()
    job.web.pages[FEED] = RuntimeError("internal detail")
    job.run()
    assert source.last_error == "Could not read this source"


def test_a_page_that_is_not_a_feed_fails(job: Job) -> None:
    source = job.source()
    job.web.pages[FEED] = b"<html></html>"
    job.run()
    assert source.last_error == "The feed could not be read"


def test_failures_accumulate_and_a_success_clears_them(job: Job) -> None:
    source = job.source()
    job.web.pages[FEED] = 500
    job.run()
    job.run()
    assert source.consecutive_failures == 2
    job.web.pages[FEED] = _rss()
    job.run()
    assert source.consecutive_failures == 0
    assert source.last_error is None


# --- Analysis ---


def test_preferences_reach_the_model_and_score_is_stored(job: Job) -> None:
    source = job.source(preferences="only databases")
    job.analyzer.result = PostAnalysis(
        title=None, summary="S", match_level="high", motivation="Because."
    )
    job.web.pages[FEED] = _rss(_item("one"))
    job.web.pages[f"{SITE}/one"] = _page()
    job.run()
    [post] = job.posts(source)
    assert job.analyzer.calls[0].preferences == "only databases"
    assert post.match_level == "high"
    assert post.motivation == "Because."


def test_no_preferences_means_no_score(job: Job) -> None:
    source = job.source()
    job.web.pages[FEED] = _rss(_item("one"))
    job.web.pages[f"{SITE}/one"] = _page()
    job.run()
    [post] = job.posts(source)
    assert job.analyzer.calls[0].preferences is None
    assert post.match_level is None
    assert post.motivation is None


def test_the_feed_title_wins_over_page_and_model(job: Job) -> None:
    source = job.source()
    job.analyzer.result = PostAnalysis(
        title="Model", summary="S", match_level=None, motivation=None
    )
    job.web.pages[FEED] = _rss(_item("one", title="Feed"))
    job.web.pages[f"{SITE}/one"] = _page("Page")
    job.run()
    assert job.posts(source)[0].title == "Feed"


def test_the_page_title_wins_over_the_model(job: Job) -> None:
    source = job.source()
    job.analyzer.result = PostAnalysis(
        title="Model", summary="S", match_level=None, motivation=None
    )
    job.web.pages[FEED] = _rss(_item("one"))
    job.web.pages[f"{SITE}/one"] = _page("Page")
    job.run()
    assert job.posts(source)[0].title == "Page"


def test_the_model_title_is_the_last_resort(job: Job) -> None:
    source = job.source()
    job.analyzer.result = PostAnalysis(
        title="Model", summary="S", match_level=None, motivation=None
    )
    job.web.pages[FEED] = _rss(_item("one"))
    job.web.pages[f"{SITE}/one"] = 404
    job.run()
    assert job.posts(source)[0].title == "Model"


def test_page_text_is_stored_and_preferred(job: Job) -> None:
    source = job.source()
    job.web.pages[FEED] = _rss(_item("one", body="A " * 150))
    job.web.pages[f"{SITE}/one"] = _page()
    job.run()
    [post] = job.posts(source)
    stored = job.store.read(post.id)
    assert stored is not None
    assert "Plenty of words" in stored
    assert "Plenty of words" in job.analyzer.calls[0].text


def test_feed_text_is_the_fallback_when_the_page_fails(job: Job) -> None:
    source = job.source()
    job.web.pages[FEED] = _rss(_item("one", body="Feed text. " * 30))
    job.web.pages[f"{SITE}/one"] = FetchError("down")
    report = job.run()
    [post] = job.posts(source)
    assert post.status == BlogPostStatus.PROCESSED.value
    assert "Feed text." in (job.store.read(post.id) or "")
    assert report.failures == 0


def test_feed_text_is_the_fallback_for_a_teaser_page(job: Job) -> None:
    job.source()
    job.web.pages[FEED] = _rss(_item("one", body="Feed text. " * 30))
    job.web.pages[f"{SITE}/one"] = b"<html><body><p>Subscribe</p></body></html>"
    job.run()
    assert "Feed text." in job.analyzer.calls[0].text


def test_thin_content_fails_without_calling_the_model(job: Job) -> None:
    source = job.source()
    job.web.pages[FEED] = _rss(_item("one", title="One", body="Short."))
    job.web.pages[f"{SITE}/one"] = b"<html><body><p>Hi</p></body></html>"
    report = job.run()
    [post] = job.posts(source)
    assert post.status == BlogPostStatus.FAILED.value
    assert post.summary is None
    assert post.title == "One"
    assert job.analyzer.calls == []
    assert report.posts_too_short == 1
    assert report.failures == 0


def test_exactly_the_minimum_length_is_analyzed(job: Job) -> None:
    job.source()
    job.web.pages[FEED] = _rss(_item("one", body="x" * MIN_TEXT_CHARS))
    job.web.pages[f"{SITE}/one"] = 404
    job.run()
    assert len(job.analyzer.calls) == 1


def test_model_failure_retries_until_failed(job: Job) -> None:
    source = job.source()
    job.analyzer.error = RuntimeError("no credits")
    job.web.pages[FEED] = _rss(_item("one"))
    job.web.pages[f"{SITE}/one"] = _page()

    for attempt in range(1, MAX_ATTEMPTS + 1):
        report = job.run()
        [post] = job.posts(source)
        assert report.failures == 1
        assert post.attempts == attempt

    assert post.status == BlogPostStatus.FAILED.value
    assert job.run().failures == 0
    assert len(job.analyzer.calls) == MAX_ATTEMPTS


def test_a_retry_reuses_the_text_file(job: Job) -> None:
    source = job.source()
    job.analyzer.error = RuntimeError("no credits")
    job.web.pages[FEED] = _rss(_item("one", body="Feed only. " * 30))
    job.web.pages[f"{SITE}/one"] = FetchError("down")
    job.run()
    assert job.web.requested.count(f"{SITE}/one") == 1

    job.analyzer.error = None
    job.web.etags.clear()
    job.run()

    [post] = job.posts(source)
    assert post.status == BlogPostStatus.PROCESSED.value
    assert job.web.requested.count(f"{SITE}/one") == 1
    assert "Feed only." in job.analyzer.calls[-1].text


def test_an_unreachable_page_with_no_feed_text_is_retried(job: Job) -> None:
    source = job.source()
    job.web.pages[FEED] = _rss(_item("one", body=""))
    job.web.pages[f"{SITE}/one"] = FetchError("down")
    report = job.run()
    [post] = job.posts(source)
    assert post.status == BlogPostStatus.PENDING.value
    assert post.attempts == 1
    assert report.failures == 1


def test_a_post_deleted_during_analysis_is_left_alone(job: Job) -> None:
    source = job.source()
    job.web.pages[FEED] = _rss(_item("one"))
    job.web.pages[f"{SITE}/one"] = _page()

    def delete_source_meanwhile(_post: object) -> PostAnalysis:
        job.session.delete(source)
        job.session.flush()
        return job.analyzer.result

    with patch.object(job.analyzer, "analyze", delete_source_meanwhile):
        report = job.run()
    assert report.posts_analyzed == 0
    assert report.failures == 0


# --- Embed ---


def _useful_post(job: Job, *, title: str | None = "One") -> tuple[BlogSource, BlogPost]:
    """A processed post the user just marked useful."""
    source = job.source()
    job.web.pages[FEED] = _rss(_item("one", title=title))
    job.web.pages[f"{SITE}/one"] = _page()
    job.run()
    [post] = job.posts(source)
    set_post_state(job.session, job.owner, post.id, BlogPostState.USEFUL)
    job.session.commit()
    return source, post


def _chunks(job: Job, post: BlogPost) -> list[str]:
    rows = job.session.execute(
        select(post_chunk_embedding.c.content)
        .where(post_chunk_embedding.c.post_id == post.id)
        .order_by(post_chunk_embedding.c.chunk_index),
    )
    return list(rows.scalars())


def test_a_useful_post_is_embedded_without_fetching(job: Job) -> None:
    _, post = _useful_post(job)
    job.web.requested.clear()
    job.web.pages[FEED] = 304

    report = job.run()

    assert report.posts_embedded == 1
    assert f"{SITE}/one" not in job.web.requested
    job.session.refresh(post)
    assert post.embed_status == BlogEmbedStatus.DONE.value
    chunks = _chunks(job, post)
    assert chunks
    assert chunks[0].startswith("Title: One\nSource: Blog\nSummary: A summary.")
    assert "Plenty of words" in chunks[0]


def test_owner_and_source_are_stored_with_the_chunks(job: Job) -> None:
    source, post = _useful_post(job)
    job.run()
    row = job.session.execute(
        select(post_chunk_embedding).where(post_chunk_embedding.c.post_id == post.id),
    ).first()
    assert row is not None
    assert row.owner_id == job.owner.uid
    assert row.source_id == source.id


def test_a_post_with_no_file_embeds_title_and_summary(job: Job) -> None:
    _, post = _useful_post(job)
    job.store.path(post.id).unlink()
    job.run()
    assert _chunks(job, post) == ["Title: One\nSource: Blog\nSummary: A summary."]


def test_a_failed_post_can_be_embedded_with_its_url_as_title(job: Job) -> None:
    source = job.source()
    job.web.pages[FEED] = _rss(_item("short", body="Short."))
    job.web.pages[f"{SITE}/short"] = 404
    job.analyzer.error = None
    job.run()
    [post] = job.posts(source)
    post.status = BlogPostStatus.FAILED.value
    job.session.commit()
    set_post_state(job.session, job.owner, post.id, BlogPostState.USEFUL)
    job.session.commit()
    job.run()
    assert _chunks(job, post)[0].startswith(f"Title: {SITE}/short\nSource: Blog")


def test_a_verdict_changed_during_embedding_wins(job: Job) -> None:
    _, post = _useful_post(job)
    real = job.embeddings.embed_documents

    def change_verdict_meanwhile(texts: list[str]) -> list[list[float]]:
        set_post_state(job.session, job.owner, post.id, BlogPostState.NOT_USEFUL)
        job.session.commit()
        return real(texts)

    with patch.object(
        type(job.embeddings), "embed_documents", lambda _, t: change_verdict_meanwhile(t)
    ):
        report = job.run()

    assert report.posts_embedded == 0
    assert report.failures == 0
    assert _chunks(job, post) == []
    job.session.refresh(post)
    assert post.embed_status == BlogEmbedStatus.NONE.value


def test_embedding_failure_retries_until_failed(job: Job) -> None:
    _, post = _useful_post(job)
    with patch.object(
        type(job.embeddings),
        "embed_documents",
        side_effect=RuntimeError("no credits"),
    ):
        for _ in range(MAX_ATTEMPTS):
            assert job.run().failures == 1
        assert job.run().failures == 0
    job.session.refresh(post)
    assert post.embed_status == BlogEmbedStatus.FAILED.value
    assert post.embed_attempts == MAX_ATTEMPTS


def test_wrong_dimension_is_a_failure_and_writes_nothing(job: Job) -> None:
    _, post = _useful_post(job)
    job.embeddings = DeterministicFakeEmbedding(size=8)
    assert job.run().failures == 1
    assert _chunks(job, post) == []


def test_embedding_again_replaces_the_chunks(job: Job) -> None:
    _, post = _useful_post(job)
    job.run()
    set_post_state(job.session, job.owner, post.id, BlogPostState.NEW)
    set_post_state(job.session, job.owner, post.id, BlogPostState.USEFUL)
    job.session.commit()
    job.run()
    count = job.session.scalar(
        select(func.count())
        .select_from(post_chunk_embedding)
        .where(post_chunk_embedding.c.post_id == post.id),
    )
    assert count == len(_chunks(job, post))
    assert count == 1


def test_a_deleted_post_loses_its_chunks(job: Job) -> None:
    source, post = _useful_post(job)
    job.run()
    post_id = post.id
    job.session.delete(source)
    job.session.commit()
    remaining = job.session.scalar(
        select(func.count())
        .select_from(post_chunk_embedding)
        .where(post_chunk_embedding.c.post_id == post_id),
    )
    assert remaining == 0


# --- Sweep ---


def test_the_sweep_removes_only_orphaned_files(job: Job) -> None:
    source = job.source()
    job.web.pages[FEED] = _rss(_item("one"))
    job.web.pages[f"{SITE}/one"] = _page()
    orphan = uuid.uuid4()
    job.store.write(orphan, "text of a deleted post")

    report = job.run()

    assert report.files_swept == 1
    assert job.store.read(orphan) is None
    [post] = job.posts(source)
    assert job.store.read(post.id) is not None


def test_a_deleted_source_loses_its_text_at_the_next_run(job: Job) -> None:
    source = job.source()
    job.web.pages[FEED] = _rss(_item("one"))
    job.web.pages[f"{SITE}/one"] = _page()
    job.run()
    [post] = job.posts(source)
    post_id = post.id
    job.session.delete(source)
    job.session.flush()
    job.run()
    assert job.store.read(post_id) is None


# --- Dry run ---


def test_dry_run_reports_and_touches_nothing(job: Job) -> None:
    source = job.source()
    job.web.etags[FEED] = '"v1"'
    job.web.pages[FEED] = _rss(_item("one"))
    orphan = uuid.uuid4()
    job.store.write(orphan, "kept in a dry run")

    report = job.run(dry_run=True)

    assert report.would_collect == [("Blog", f"{SITE}/one")]
    assert job.posts(source) == []
    assert source.etag is None
    assert source.last_fetched_at is None
    assert job.analyzer.calls == []
    assert job.store.read(orphan) is not None


def test_dry_run_does_not_record_failures(job: Job) -> None:
    source = job.source()
    job.web.pages[FEED] = 500
    assert job.run(dry_run=True).failures == 1
    assert source.consecutive_failures == 0


# --- Lock ---


def test_only_one_run_holds_the_lock(request: pytest.FixtureRequest) -> None:
    engine: Engine = request.getfixturevalue("_pg_engine")
    with advisory_lock(engine) as first:
        assert first
        with advisory_lock(engine) as second:
            assert not second
    with advisory_lock(engine) as again:
        assert again
