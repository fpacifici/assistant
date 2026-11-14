"""Tests for URL normalization."""

from __future__ import annotations

import pytest

from assistant.web.urls import canonical_path, is_http_url, strip_tracking

# --- canonical_path ---


def test_query_order_and_fragment_do_not_matter() -> None:
    assert canonical_path("https://a.example/x?b=2&a=1#top") == "/x?a=1&b=2"


def test_tracking_and_trailing_slash_do_not_matter() -> None:
    assert canonical_path("https://a.example/x/?utm_source=rss&fbclid=1") == "/x"


# --- strip_tracking ---


def test_strip_tracking_keeps_everything_else() -> None:
    assert (
        strip_tracking("https://A.example/x/?utm_medium=a&id=3&ref=hn#part")
        == "https://A.example/x/?id=3#part"
    )


# --- is_http_url ---


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://a.example/x", True),
        ("HTTP://a.example", True),
        ("ftp://a.example", False),
        ("a.example/x", False),
        ("https://", False),
    ],
)
def test_is_http_url(value: str, expected: bool) -> None:
    assert is_http_url(value) is expected
