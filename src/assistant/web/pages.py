"""Turns downloaded HTML into plain text, for blogs and the reading list.

`trafilatura` only ever sees HTML we downloaded through the safe fetcher: its
own downloading and discovery helpers bypass it, and are not used. No script
in a page runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import trafilatura
from bs4 import BeautifulSoup
from trafilatura.utils import load_html


def parse_date(value: str | None) -> datetime | None:
    """Parse an ISO 8601 date or datetime, as UTC when it has no zone."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class ExtractedPage:
    """What a page yields. Any of it can be missing."""

    text: str | None = None
    title: str | None = None
    published_at: datetime | None = None


def _date_config() -> dict[str, object]:
    """Date search settings: a date the page states, or none.

    The default extensive search guesses (a copyright year becomes January
    1st), and a dateless sitemap post has to be skipped, not misdated. The
    margin is for a page dated in a time zone ahead of this machine.
    """
    tomorrow = datetime.now(UTC) + timedelta(days=1)
    return {
        "original_date": True,
        "extensive_search": False,
        "max_date": tomorrow.strftime("%Y-%m-%d"),
    }


def extract_page(html: bytes, url: str) -> ExtractedPage:
    """Extract a page's main text, title and date.

    Args:
        html: The downloaded page.
        url: Its URL.

    Returns:
        The extracted fields. The text is markdown, whose headings the
        embedding step splits on.
    """
    tree = load_html(html)
    if tree is None:
        return ExtractedPage()
    text = trafilatura.extract(
        html,
        url=url,
        output_format="markdown",
        include_comments=False,
        include_tables=True,
    )
    metadata = trafilatura.extract_metadata(
        tree, default_url=url, date_config=_date_config()
    )
    return ExtractedPage(
        text=text.strip() if text else None,
        title=(metadata.title or "").strip() or None,
        published_at=parse_date(metadata.date),
    )


def html_to_text(html: str) -> str:
    """Strip a feed's HTML fragment down to its text."""
    return BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
