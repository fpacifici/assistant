"""Highlighted snippets of matching text.

Built in Python rather than with Postgres' `ts_headline`: the index holds
accent-folded text, so highlighting has to match folded query words against
the original characters (``perche`` highlights ``Perché``). Snippets are
returned as plain-text segments, never HTML, so clients render the
highlight markup themselves.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from assistant.search.analysis import tokens_with_offsets

if TYPE_CHECKING:
    from assistant.search.query import SearchQuery


@dataclass(frozen=True)
class SnippetSegment:
    """A run of snippet text, highlighted when it matched the query."""

    text: str
    highlighted: bool


def _matches(token: str, query: SearchQuery) -> bool:
    if token in query.terms or any(token in phrase for phrase in query.phrases):
        return True
    return query.prefix is not None and token.startswith(query.prefix)


SNIPPET_WIDTH = 160
ELLIPSIS = "…"


def _window(
    text: str, tokens: list[tuple[str, int, int]], anchor: int, width: int
) -> tuple[int, int]:
    """A span of at most `width` chars around `anchor`, on word boundaries."""
    if len(text) <= width:
        return 0, len(text)
    start = 0
    lead = anchor - width // 3
    if lead > 0:
        start = next((s for _, s, _ in tokens if s >= lead), anchor)
    end = start + width
    if end >= len(text):
        return start, len(text)
    word_ends = [e for _, s, e in tokens if s >= start and e <= end]
    return start, word_ends[-1] if word_ends else end


def build_segments(
    text: str,
    query: SearchQuery,
    *,
    width: int = SNIPPET_WIDTH,
) -> tuple[SnippetSegment, ...]:
    """Highlight the words `query` matches in a window of `text`.

    The window is at most `width` characters, cut on word boundaries around
    the first match (or at the beginning when nothing matches), with an
    ellipsis wherever text was cut off.
    """
    tokens = tokens_with_offsets(text)
    hits = [(s, e) for token, s, e in tokens if _matches(token, query)]
    start, end = _window(text, tokens, hits[0][0] if hits else 0, width)

    segments: list[SnippetSegment] = []

    def plain(chunk: str) -> None:
        if not chunk:
            return
        if segments and not segments[-1].highlighted:
            chunk = segments.pop().text + chunk
        segments.append(SnippetSegment(chunk, highlighted=False))

    if start > 0:
        plain(ELLIPSIS)
    cursor = start
    for hit_start, hit_end in hits:
        if hit_start < start or hit_end > end:
            continue
        plain(text[cursor:hit_start])
        segments.append(SnippetSegment(text[hit_start:hit_end], highlighted=True))
        cursor = hit_end
    plain(text[cursor:end])
    if end < len(text):
        plain(ELLIPSIS)
    return tuple(segments)
