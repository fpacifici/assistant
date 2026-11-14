"""Tests for describing why a site rejected a request."""

from __future__ import annotations

import pytest

from assistant.web.fetch import FetchResult
from assistant.web.rejection import (
    MAX_VALUE_CHARS,
    describe_rejection,
    page_title,
    summarize_rejection,
)

URL = "https://medium.com/some/post"

CLOUDFLARE_CHALLENGE = (
    b"<!DOCTYPE html><html><head><title>Just a moment...</title>"
    b'<meta http-equiv="content-security-policy" content="script-src '
    b'https://challenges.cloudflare.com"></head><body></body></html>'
)


def _result(
    status: int = 403, content: bytes = b"", headers: dict[str, str] | None = None
) -> FetchResult:
    return FetchResult(url=URL, status=status, content=content, headers=headers or {})


# --- Page title ---


def test_page_title_is_cleaned_and_cut() -> None:
    assert page_title(b"<html><TITLE>\n Just  a\tmoment\x00 </TITLE>") == "Just a moment"
    assert page_title(b"<title>" + b"x" * 500 + b"</title>") == "x" * MAX_VALUE_CHARS
    assert page_title(b"no title here") is None
    assert page_title(b"<title> </title>") is None


# --- Blockers ---


def test_cloudflare_challenge_from_the_header() -> None:
    details = describe_rejection(
        _result(
            headers={
                "server": "cloudflare",
                "cf-mitigated": "challenge",
                "cf-ray": "abc-LHR",
            }
        )
    )
    assert details["rejection.blocker"] == "cloudflare_challenge"
    assert details["http.header.cf-ray"] == "abc-LHR"


def test_cloudflare_challenge_from_the_body() -> None:
    details = describe_rejection(_result(content=CLOUDFLARE_CHALLENGE))
    assert details["rejection.blocker"] == "cloudflare_challenge"
    assert details["rejection.title"] == "Just a moment..."


def test_cloudflare_block_page() -> None:
    details = describe_rejection(
        _result(
            content=b"<title>Attention Required! | Cloudflare</title>",
            headers={"server": "cloudflare"},
        )
    )
    assert details["rejection.blocker"] == "cloudflare_block"


@pytest.mark.parametrize(
    ("headers", "blocker"),
    [
        ({"x-datadome": "protected"}, "datadome"),
        ({"x-amzn-waf-action": "challenge"}, "aws_waf"),
        ({"server": "AkamaiGHost"}, "akamai"),
        ({"x-iinfo": "1-2-3"}, "imperva"),
        ({"server": "nginx"}, "none_detected"),
    ],
)
def test_other_blockers(headers: dict[str, str], blocker: str) -> None:
    assert describe_rejection(_result(headers=headers))["rejection.blocker"] == blocker


def test_a_challenge_title_with_no_known_blocker() -> None:
    details = describe_rejection(_result(content=b"<title>Access Denied</title>"))
    assert details["rejection.blocker"] == "unknown_challenge"


# --- What is kept ---


def test_only_diagnostic_headers_are_kept() -> None:
    details = describe_rejection(
        _result(
            status=429,
            content=b"slow down",
            headers={
                "retry-after": "120",
                "set-cookie": "__cf_bm=secret",
                "x-custom": "1",
            },
        )
    )
    assert details == {
        "http.status": 429,
        "http.url": URL,
        "rejection.blocker": "none_detected",
        "rejection.body_bytes": 9,
        "http.header.retry-after": "120",
    }


def test_header_values_are_cleaned() -> None:
    details = describe_rejection(_result(headers={"server": "evil\r\nInjected: 1"}))
    assert details["http.header.server"] == "evil Injected: 1"


def test_summary_line() -> None:
    details = describe_rejection(
        _result(
            content=CLOUDFLARE_CHALLENGE,
            headers={
                "server": "cloudflare",
                "cf-mitigated": "challenge",
                "cf-ray": "abc",
            },
        )
    )
    assert summarize_rejection(details) == (
        "HTTP 403, cloudflare_challenge, title='Just a moment...', "
        "server=cloudflare, cf-mitigated=challenge, cf-ray=abc"
    )
