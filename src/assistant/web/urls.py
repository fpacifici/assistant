"""URL normalization shared by blogs and the reading list.

Two spellings of one link should compare equal: tracking parameters
(`utm_*`, `fbclid`, ...) are dropped, the other query parameters are sorted,
and the trailing slash and the fragment don't count. Any other query
parameter counts, which errs on the side of keeping two links apart.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_PREFIXES = ("utm_", "mc_", "pk_", "mtm_", "at_")
_TRACKING_PARAMS = frozenset(
    {
        "cmpid",
        "dclid",
        "fbclid",
        "gclid",
        "igshid",
        "msclkid",
        "ref",
        "ref_src",
        "share",
        "source",
        "src",
        "twclid",
        "yclid",
    }
)


def _is_tracking(name: str) -> bool:
    lowered = name.lower()
    return lowered in _TRACKING_PARAMS or lowered.startswith(_TRACKING_PREFIXES)


def canonical_path(url: str) -> str:
    """The domain-free identity of a URL: its path and identifying query.

    The trailing slash and the fragment are dropped, and query parameters are
    sorted, so spelling variants of one link compare equal.
    """
    parts = urlsplit(url)
    path = parts.path.rstrip("/") or "/"
    query = sorted(
        (name, value)
        for name, value in parse_qsl(parts.query, keep_blank_values=True)
        if not _is_tracking(name)
    )
    return f"{path}?{urlencode(query)}" if query else path


def strip_tracking(url: str) -> str:
    """The URL without its tracking parameters, otherwise as given."""
    parts = urlsplit(url)
    query = [
        (name, value)
        for name, value in parse_qsl(parts.query, keep_blank_values=True)
        if not _is_tracking(name)
    ]
    return urlunsplit(parts._replace(query=urlencode(query)))


def is_http_url(value: str) -> bool:
    """Whether a string is an absolute `http(s)` URL."""
    try:
        parts = urlsplit(value)
    except ValueError:
        return False
    return parts.scheme.lower() in {"http", "https"} and bool(parts.netloc)
