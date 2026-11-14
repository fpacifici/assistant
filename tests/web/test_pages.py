"""Tests for extracting text from pages."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from assistant.web.pages import extract_page, html_to_text, parse_date

BODY = " ".join(f"This is sentence number {n} of a fine article." for n in range(40))
PAGE = f"""<html><head><title>Page title</title>
<meta property="article:published_time" content="2024-03-01T10:00:00+00:00">
<script>alert("never runs")</script></head>
<body><nav><a href="/">Home</a></nav><article><h1>Page title</h1>
<h2>A section</h2><p>{BODY}</p></article></body></html>""".encode()


def test_extracts_text_title_and_date() -> None:
    page = extract_page(PAGE, "https://blog.example.com/post")
    assert page.title == "Page title"
    assert page.published_at == datetime(2024, 3, 1, tzinfo=UTC)
    assert page.text is not None
    assert "sentence number 7" in page.text
    assert "never runs" not in page.text
    assert "## A section" in page.text


def test_a_date_later_today_in_another_time_zone_is_kept() -> None:
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).date().isoformat()
    page = PAGE.replace(b"2024-03-01T10:00:00", f"{tomorrow}T00:30:00".encode())
    assert extract_page(page, "https://x.example/a").published_at is not None


def test_a_copyright_year_is_not_a_date() -> None:
    page = (
        f"<html><head><title>T</title></head><body><article><p>{BODY}</p></article>"
        "<footer>Copyright 2024 Someone. Last year was 2023.</footer></body></html>"
    ).encode()
    assert extract_page(page, "https://x.example/a").published_at is None


def test_a_page_with_nothing_to_extract() -> None:
    page = extract_page(b"", "https://blog.example.com/post")
    assert page.text is None
    assert page.title is None
    assert page.published_at is None


def test_html_to_text() -> None:
    assert html_to_text("<p>One <b>two</b></p><p>three</p>") == "One\ntwo\nthree"


# --- Dates ---


def test_parse_date() -> None:
    assert parse_date("2024-03-01T10:00:00Z") == datetime(2024, 3, 1, 10, tzinfo=UTC)
    assert parse_date("2024-03-01") == datetime(2024, 3, 1, tzinfo=UTC)
    assert parse_date("soon") is None
    assert parse_date(None) is None
