"""Tests for resolving a URL to a feed or sitemap."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from assistant.blogs import discovery
from assistant.blogs.discovery import (
    parse_date,
    parse_feed,
    parse_sitemap,
    resolve_source,
)
from assistant.blogs.exceptions import BlockedUrlError, FetchError, SourceResolutionError
from assistant.models.schema import BlogSourceKind
from tests.blogs.fakes import FakeWeb

SITE = "https://blog.example.com"

RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel>
  <title>Example Blog</title><link>https://blog.example.com/</link>
  <item><title>Hello</title><link>https://blog.example.com/2024/hello/</link></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Atom Blog</title>
  <entry><title>One</title><link href="https://blog.example.com/one"/></entry>
</feed>"""

PLAIN_HTML = b"<html><head><title>A blog</title></head><body>Hi</body></html>"

ADVERTISING_HTML = b"""<html><head><title>Page title</title>
<link rel="stylesheet" href="/style.css">
<link rel="alternate" type="application/rss+xml" href="/feed.xml">
</head><body></body></html>"""

SITEMAP = b"""<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://blog.example.com/a</loc><lastmod>2024-03-01</lastmod></url>
  <url><loc>https://blog.example.com/b</loc></url>
</urlset>"""

SITEMAP_INDEX = b"""<?xml version="1.0"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://blog.example.com/posts.xml</loc></sitemap>
</sitemapindex>"""


@pytest.fixture
def web() -> Iterator[FakeWeb]:
    fake = FakeWeb({})
    with patch.object(discovery, "fetch", fake):
        yield fake


# --- Feeds ---


def test_url_is_a_feed(web: FakeWeb) -> None:
    web.pages[f"{SITE}/rss"] = RSS
    resolved = resolve_source(f"{SITE}/rss")
    assert resolved.feed_url == f"{SITE}/rss"
    assert resolved.kind is BlogSourceKind.FEED
    assert resolved.title == "Example Blog"


def test_atom_is_a_feed(web: FakeWeb) -> None:
    web.pages[f"{SITE}/atom"] = ATOM
    assert resolve_source(f"{SITE}/atom").title == "Atom Blog"


def test_feed_advertised_by_the_page(web: FakeWeb) -> None:
    web.pages[SITE] = ADVERTISING_HTML
    web.pages[f"{SITE}/feed.xml"] = RSS
    resolved = resolve_source(SITE)
    assert resolved.feed_url == f"{SITE}/feed.xml"
    assert resolved.kind is BlogSourceKind.FEED
    assert resolved.title == "Example Blog"


def test_advertised_feed_without_a_title_uses_the_page_title(web: FakeWeb) -> None:
    web.pages[SITE] = ADVERTISING_HTML
    web.pages[f"{SITE}/feed.xml"] = RSS.replace(b"<title>Example Blog</title>", b"")
    assert resolve_source(SITE).title == "Page title"


def test_broken_advertised_feed_falls_through_to_the_sitemap(web: FakeWeb) -> None:
    web.pages[SITE] = ADVERTISING_HTML
    web.pages[f"{SITE}/feed.xml"] = FetchError("down")
    web.pages[f"{SITE}/sitemap.xml"] = SITEMAP
    assert resolve_source(SITE).kind is BlogSourceKind.SITEMAP


# --- Sitemaps ---


def test_sitemap_at_the_well_known_path(web: FakeWeb) -> None:
    web.pages[SITE] = PLAIN_HTML
    web.pages[f"{SITE}/sitemap.xml"] = SITEMAP
    resolved = resolve_source(SITE)
    assert resolved.feed_url == f"{SITE}/sitemap.xml"
    assert resolved.kind is BlogSourceKind.SITEMAP
    assert resolved.title == "A blog"


def test_sitemap_named_by_robots(web: FakeWeb) -> None:
    web.pages[f"{SITE}/blog"] = PLAIN_HTML
    web.pages[f"{SITE}/robots.txt"] = f"Sitemap: {SITE}/custom.xml\n".encode()
    web.pages[f"{SITE}/custom.xml"] = SITEMAP_INDEX
    assert resolve_source(f"{SITE}/blog").feed_url == f"{SITE}/custom.xml"


# --- Failures ---


def test_nothing_found(web: FakeWeb) -> None:
    web.pages[SITE] = PLAIN_HTML
    with pytest.raises(SourceResolutionError, match="No feed found"):
        resolve_source(SITE)


@pytest.mark.parametrize(
    "failure", [FetchError("boom"), BlockedUrlError("This address is not allowed")]
)
def test_unreachable_url_gives_a_generic_error(web: FakeWeb, failure: FetchError) -> None:
    web.pages[SITE] = failure
    with pytest.raises(SourceResolutionError) as caught:
        resolve_source(SITE)
    assert str(caught.value) == "Could not reach this URL"


def test_http_error_is_unreachable(web: FakeWeb) -> None:
    with pytest.raises(SourceResolutionError, match="Could not reach"):
        resolve_source(SITE)
    assert web.requested == [SITE]


def test_errors_never_echo_page_content(web: FakeWeb) -> None:
    web.pages[SITE] = b"<html><title>internal-secret</title></html>"
    with pytest.raises(SourceResolutionError) as caught:
        resolve_source(SITE)
    assert "internal-secret" not in str(caught.value)


# --- Single posts ---


@pytest.mark.parametrize(
    "head",
    [
        b'<meta property="og:type" content="article">',
        b'<script type="application/ld+json">{"@type": "BlogPosting"}</script>',
        b'<script type="application/ld+json">{"@graph": [{"@type": "WebSite"},'
        b' {"@type": ["Article"]}]}</script>',
        b'<script type="application/ld+json">[{"@type": "NewsArticle"}]</script>',
    ],
)
def test_single_post_is_refused_before_following_its_feed(
    web: FakeWeb, head: bytes
) -> None:
    web.pages[f"{SITE}/2024/hello"] = (
        b'<html><head><link rel="alternate" type="application/rss+xml" '
        b'href="/feed.xml">' + head + b"</head></html>"
    )
    web.pages[f"{SITE}/feed.xml"] = RSS
    with pytest.raises(SourceResolutionError, match="single post"):
        resolve_source(f"{SITE}/2024/hello")
    assert f"{SITE}/feed.xml" not in web.requested


def test_page_listed_as_a_feed_entry_is_a_single_post(web: FakeWeb) -> None:
    web.pages[f"{SITE}/2024/hello/"] = ADVERTISING_HTML
    web.pages[f"{SITE}/feed.xml"] = RSS
    with pytest.raises(SourceResolutionError, match="single post"):
        resolve_source(f"{SITE}/2024/hello/")


def test_home_page_is_not_a_single_post_for_a_linkless_entry(web: FakeWeb) -> None:
    web.pages[SITE] = ADVERTISING_HTML
    web.pages[f"{SITE}/feed.xml"] = RSS.replace(
        b"<link>https://blog.example.com/2024/hello/</link>", b""
    )
    assert resolve_source(SITE).kind is BlogSourceKind.FEED


def test_malformed_json_ld_is_ignored(web: FakeWeb) -> None:
    web.pages[SITE] = (
        b'<html><head><script type="application/ld+json">{oops</script></head></html>'
    )
    with pytest.raises(SourceResolutionError, match="No feed found"):
        resolve_source(SITE)


# --- Parsers ---


def test_html_is_not_a_feed() -> None:
    assert parse_feed(PLAIN_HTML) is None


def test_feed_parser_never_opens_its_input_as_a_path() -> None:
    assert parse_feed(b"/etc/passwd") is None


def test_sitemap_pages() -> None:
    sitemap = parse_sitemap(SITEMAP)
    assert sitemap is not None
    assert [page.url for page in sitemap.pages] == [f"{SITE}/a", f"{SITE}/b"]
    assert sitemap.pages[0].lastmod == datetime(2024, 3, 1, tzinfo=UTC)
    assert sitemap.pages[1].lastmod is None


def test_sitemap_index_children() -> None:
    sitemap = parse_sitemap(SITEMAP_INDEX)
    assert sitemap is not None
    assert [child.url for child in sitemap.children] == [f"{SITE}/posts.xml"]


def test_other_xml_is_not_a_sitemap() -> None:
    assert parse_sitemap(b"<html></html>") is None
    assert parse_sitemap(b"not xml") is None


def test_entity_expansion_is_refused() -> None:
    bomb = (
        b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">]>'
        b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        b"<url><loc>&lol;</loc></url></urlset>"
    )
    assert parse_sitemap(bomb) is None


def test_parse_date() -> None:
    assert parse_date("2024-03-01T10:00:00Z") == datetime(2024, 3, 1, 10, tzinfo=UTC)
    assert parse_date("2024-03-01") == datetime(2024, 3, 1, tzinfo=UTC)
    assert parse_date("soon") is None
    assert parse_date(None) is None
