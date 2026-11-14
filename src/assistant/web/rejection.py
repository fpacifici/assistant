"""Why a site rejected a request: for logs, never for users.

A 4xx or 5xx says little on its own. Most rejections of a fetch for a page a
person could open come from bot protection in front of the site (Cloudflare,
Akamai, DataDome, AWS WAF), which answers with a challenge page instead of the
content. `describe_rejection` names the protection when the response gives it
away, and keeps the headers and page title that explain the rest.

Everything here comes from the response, so it is untrusted: values are cut
short and stripped of control characters, and the result only goes to logs.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from assistant.web.fetch import FetchResult

# Headers that tell who answered and why. Never cookies or anything that
# could carry a credential.
DIAGNOSTIC_HEADERS = (
    "server",
    "content-type",
    "content-length",
    "retry-after",
    "via",
    "x-cache",
    "cf-ray",
    "cf-mitigated",
    "x-amz-cf-id",
    "x-amzn-waf-action",
    "x-datadome",
    "x-iinfo",
    "akamai-grn",
    "www-authenticate",
)
MAX_VALUE_CHARS = 200
# `rejection.blocker` when nothing in the response names a protection.
NO_BLOCKER = "none_detected"
# Enough to find a <title> in the head of a challenge page.
_TITLE_SCAN_BYTES = 64 * 1024
_TITLE = re.compile(rb"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")

_CHALLENGE_TITLES = (
    "just a moment",
    "attention required",
    "access denied",
    "verifying you are human",
    "pardon our interruption",
)


def _clean(value: str) -> str:
    return " ".join(_CONTROL.sub(" ", value).split())[:MAX_VALUE_CHARS]


def page_title(content: bytes) -> str | None:
    """The `<title>` of an HTML body, if it has one near the top."""
    match = _TITLE.search(content[:_TITLE_SCAN_BYTES])
    if match is None:
        return None
    return _clean(match.group(1).decode("utf-8", errors="replace")) or None


def _blocker(result: FetchResult, title: str | None) -> str:
    """Which protection answered, from the headers and body it sends."""
    headers = result.headers
    server = headers.get("server", "").lower()
    head = result.content[:_TITLE_SCAN_BYTES]
    challenge_title = title is not None and title.lower().startswith(_CHALLENGE_TITLES)
    # In order: the first sign that matches names the blocker.
    signs = (
        (
            headers.get("cf-mitigated") == "challenge"
            or b"challenges.cloudflare.com" in head,
            "cloudflare_challenge",
        ),
        (server == "cloudflare" and challenge_title, "cloudflare_block"),
        ("x-datadome" in headers or b"captcha-delivery.com" in head, "datadome"),
        ("x-amzn-waf-action" in headers, "aws_waf"),
        ("akamai-grn" in headers or server.startswith("akamaighost"), "akamai"),
        ("x-iinfo" in headers, "imperva"),
        (challenge_title, "unknown_challenge"),
    )
    return next((name for matched, name in signs if matched), NO_BLOCKER)


def describe_rejection(result: FetchResult) -> dict[str, str | int]:
    """What a rejected response says about why, as flat log attributes.

    Args:
        result: A response with an error status.

    Returns:
        `http.status`, the final `http.url`, `rejection.blocker` (the
        protection that answered, or `none_detected`), `rejection.title`
        (the page title) when there is one, `rejection.body_bytes`, and one
        `http.header.<name>` per diagnostic header present.
    """
    title = page_title(result.content)
    details: dict[str, str | int] = {
        "http.status": result.status,
        "http.url": _clean(result.url),
        "rejection.blocker": _blocker(result, title),
        "rejection.body_bytes": len(result.content),
    }
    if title:
        details["rejection.title"] = title
    for name in DIAGNOSTIC_HEADERS:
        value = result.headers.get(name)
        if value:
            details[f"http.header.{name}"] = _clean(value)
    return details


def summarize_rejection(details: dict[str, str | int]) -> str:
    """One readable line from `describe_rejection`, for the log message."""
    parts = [f"HTTP {details['http.status']}", str(details["rejection.blocker"])]
    if "rejection.title" in details:
        parts.append(f"title={details['rejection.title']!r}")
    for key in ("server", "cf-mitigated", "cf-ray", "retry-after"):
        value = details.get(f"http.header.{key}")
        if value:
            parts.append(f"{key}={value}")
    return ", ".join(parts)
