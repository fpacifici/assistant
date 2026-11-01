"""Turns the URL a user typed into something the job can collect.

Registration tries, in order: the URL as a feed, a feed advertised by the
page, the site's sitemap. A single post is refused even though its page
advertises the blog's feed, because the user asked for one post, not a blog.

Everything is read through the safe fetcher and only parsed as data. Errors
are generic and never echo the fetched content.
"""

from __future__ import annotations

import io
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import feedparser
from bs4 import BeautifulSoup
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import ParseError

from assistant.blogs.exceptions import FetchError, SourceResolutionError
from assistant.blogs.fetch import fetch
from assistant.blogs.identity import canonical_path
from assistant.models.schema import BlogSourceKind

if TYPE_CHECKING:
    # Only a type: all parsing goes through defusedxml.
    from xml.etree.ElementTree import Element  # nosec B405

logger = logging.getLogger(__name__)

MAX_TITLE_LENGTH = 500

_FEED_TYPES = frozenset({"application/rss+xml", "application/atom+xml"})
_ARTICLE_TYPES = frozenset({"Article", "BlogPosting", "NewsArticle", "TechArticle"})
_WELL_KNOWN_SITEMAPS = ("/sitemap.xml", "/sitemap_index.xml", "/wp-sitemap.xml")
_UNREACHABLE = "Could not reach this URL"
_NO_FEED = "No feed found at this URL"
_SINGLE_POST = "This looks like a single post. Enter the address of the blog instead"


@dataclass(frozen=True, slots=True)
class ResolvedSource:
    """What a URL resolved to."""

    feed_url: str
    kind: BlogSourceKind
    title: str


@dataclass(frozen=True, slots=True)
class SitemapEntry:
    """One `<url>` or `<sitemap>` of a sitemap."""

    url: str
    lastmod: datetime | None


@dataclass(frozen=True, slots=True)
class Sitemap:
    """A parsed sitemap: pages, or for a sitemap index, more sitemaps."""

    pages: list[SitemapEntry]
    children: list[SitemapEntry]


def parse_feed(content: bytes) -> Any | None:  # noqa: ANN401
    """Parse a feed, or return `None` if the content is not one.

    The bytes go in as a stream on purpose: given a plain value, feedparser
    tries it as a URL or a local file name.

    Returns:
        feedparser's result (dynamically typed).
    """
    parsed = feedparser.parse(io.BytesIO(content))
    if not parsed.get("version"):
        return None
    if not parsed.entries and not parsed.feed.get("title"):
        return None
    return parsed


def parse_date(value: str | None) -> datetime | None:
    """Parse an ISO 8601 date or datetime, as UTC when it has no zone."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _local_name(element: Element) -> str:
    return element.tag.rsplit("}", maxsplit=1)[-1]


def _entries(root: Element) -> list[SitemapEntry]:
    entries: list[SitemapEntry] = []
    for item in root:
        fields = {_local_name(child): (child.text or "").strip() for child in item}
        if fields.get("loc"):
            entries.append(SitemapEntry(fields["loc"], parse_date(fields.get("lastmod"))))
    return entries


def parse_sitemap(content: bytes) -> Sitemap | None:
    """Parse a sitemap or sitemap index, or return `None` if it is neither."""
    try:
        root = ElementTree.fromstring(content, forbid_dtd=True)
    except (ParseError, DefusedXmlException, ValueError):
        return None
    name = _local_name(root)
    if name == "urlset":
        return Sitemap(pages=_entries(root), children=[])
    if name == "sitemapindex":
        return Sitemap(pages=[], children=_entries(root))
    return None


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def parse_robots(content: bytes) -> RobotFileParser:
    """Parse a robots.txt. Parsing it ourselves keeps its fetch safe."""
    robots = RobotFileParser()
    robots.parse(content.decode("utf-8", errors="replace").splitlines())
    # `can_fetch` refuses everything until this is set, which `parse` only
    # does when it sees a rule, so an empty file would block the whole site.
    robots.modified()
    return robots


def _sitemap_candidates(page_url: str) -> list[str]:
    origin = _origin(page_url)
    advertised: list[str] = []
    try:
        result = fetch(f"{origin}/robots.txt")
        if result.ok:
            advertised = parse_robots(result.content).site_maps() or []
    except FetchError:
        logger.debug("No robots.txt for %s", origin)
    return [*advertised, *(f"{origin}{path}" for path in _WELL_KNOWN_SITEMAPS)]


def _find_sitemap(page_url: str) -> str | None:
    for candidate in _sitemap_candidates(page_url):
        try:
            result = fetch(candidate)
        except FetchError:
            continue
        if not result.ok:
            continue
        sitemap = parse_sitemap(result.content)
        if sitemap is not None and (sitemap.pages or sitemap.children):
            return result.url
    return None


def _json_ld_types(soup: BeautifulSoup) -> set[str]:
    """The top-level `@type`s declared by a page's JSON-LD blocks."""
    types: set[str] = set()
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except ValueError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            graph = item.get("@graph")
            for node in graph if isinstance(graph, list) else [item]:
                kind = node.get("@type") if isinstance(node, dict) else None
                kinds = kind if isinstance(kind, list) else [kind]
                types.update(k for k in kinds if isinstance(k, str))
    return types


def _is_single_post(soup: BeautifulSoup) -> bool:
    og_type = soup.find("meta", property="og:type")
    if og_type is not None and str(og_type.get("content", "")).lower() == "article":
        return True
    return bool(_json_ld_types(soup) & _ARTICLE_TYPES)


def _advertised_feeds(soup: BeautifulSoup, page_url: str) -> list[str]:
    feeds: list[str] = []
    for link in soup.find_all("link", href=True):
        link_type = str(link.get("type", "")).lower()
        if "alternate" in (link.get("rel") or ()) and link_type in _FEED_TYPES:
            feeds.append(urljoin(page_url, str(link["href"])))
    return feeds


def _feed_lists_page(parsed: Any, page_url: str) -> bool:  # noqa: ANN401
    """Whether a feed has an entry at this page's URL: the page is a post."""
    page = canonical_path(page_url)
    if page == "/":
        return False
    links = (str(entry.get("link", "")) for entry in parsed.entries)
    return any(link and canonical_path(link) == page for link in links)


def _feed_title(parsed: Any, fallback: str) -> str:  # noqa: ANN401
    return str(parsed.feed.get("title") or "").strip() or fallback


def _page_title(soup: BeautifulSoup) -> str | None:
    title = soup.title.get_text(strip=True) if soup.title else ""
    return title or None


def _resolve_advertised(soup: BeautifulSoup, page_url: str) -> ResolvedSource | None:
    fallback = _page_title(soup) or urlsplit(page_url).netloc
    for feed_url in _advertised_feeds(soup, page_url):
        try:
            result = fetch(feed_url)
        except FetchError:
            continue
        parsed = parse_feed(result.content) if result.ok else None
        if parsed is None:
            continue
        if _feed_lists_page(parsed, page_url):
            raise SourceResolutionError(_SINGLE_POST)
        return ResolvedSource(
            result.url,
            BlogSourceKind.FEED,
            _feed_title(parsed, fallback)[:MAX_TITLE_LENGTH],
        )
    return None


def resolve_source(url: str) -> ResolvedSource:
    """Resolve a user's URL to a feed or sitemap.

    Args:
        url: A feed, or a blog page.

    Returns:
        The resolved source.

    Raises:
        SourceResolutionError: If the URL can't be reached, is a single post,
            or has nothing to collect. The message is safe to show.
    """
    try:
        page = fetch(url)
        page.raise_for_status()
    except FetchError as exc:
        raise SourceResolutionError(_UNREACHABLE) from exc

    host = urlsplit(page.url).netloc
    parsed = parse_feed(page.content)
    if parsed is not None:
        return ResolvedSource(
            page.url,
            BlogSourceKind.FEED,
            _feed_title(parsed, host)[:MAX_TITLE_LENGTH],
        )

    soup = BeautifulSoup(page.content, "html.parser")
    if _is_single_post(soup):
        raise SourceResolutionError(_SINGLE_POST)
    resolved = _resolve_advertised(soup, page.url)
    if resolved is not None:
        return resolved

    sitemap_url = _find_sitemap(page.url)
    if sitemap_url is None:
        raise SourceResolutionError(_NO_FEED)
    title = (_page_title(soup) or host)[:MAX_TITLE_LENGTH]
    return ResolvedSource(sitemap_url, BlogSourceKind.SITEMAP, title)
