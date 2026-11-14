"""What makes two feed entries the same post.

A post is identified within its source by `post_key`, which survives a domain
move: the key is the SHA-256 of the entry's guid or, when there is no guid or
the guid is a URL, of the URL's path. The query string counts only when it
identifies the post (`?p=123`), not when it tracks a click (`?utm_source=x`):
see `assistant.web.urls.canonical_path`.
"""

from __future__ import annotations

import hashlib

from assistant.web.urls import canonical_path, is_http_url


def post_key(url: str, guid: str | None = None) -> str:
    """Return the key identifying a post within its source.

    Args:
        url: The post's URL.
        guid: The feed's guid for the entry, if it has one.

    Returns:
        A hex SHA-256 digest.
    """
    guid = (guid or "").strip()
    identity = guid if guid and not is_http_url(guid) else canonical_path(guid or url)
    return hashlib.sha256(identity.encode()).hexdigest()
