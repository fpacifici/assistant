"""What makes two feed entries the same post.

A post is identified within its source by `post_key`, which survives a domain
move: the key is the SHA-256 of the entry's guid or, when there is no guid or
the guid is a URL, of the URL's path. The query string counts only when it
identifies the post (`?p=123`), not when it tracks a click (`?utm_source=x`).
"""

from __future__ import annotations

import hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit

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


def _is_http_url(value: str) -> bool:
    try:
        parts = urlsplit(value)
    except ValueError:
        return False
    return parts.scheme.lower() in {"http", "https"} and bool(parts.netloc)


def post_key(url: str, guid: str | None = None) -> str:
    """Return the key identifying a post within its source.

    Args:
        url: The post's URL.
        guid: The feed's guid for the entry, if it has one.

    Returns:
        A hex SHA-256 digest.
    """
    guid = (guid or "").strip()
    identity = guid if guid and not _is_http_url(guid) else canonical_path(guid or url)
    return hashlib.sha256(identity.encode()).hexdigest()
