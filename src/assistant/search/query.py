"""Parse a raw search string into a structured `SearchQuery`.

Grammar (see docs/specs/0007-search.md):

- bare words: all must match
- ``"quoted phrase"``: words adjacent and in order; an unterminated quote
  runs to the end of the string
- ``tag:name`` / ``tag:"multi word"``: the caller's tag, all must match
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from assistant.notes.exceptions import InvalidTagNameError
from assistant.notes.tags import normalize_tag_name
from assistant.search.analysis import analyze


class EmptySearchQueryError(ValueError):
    """The search string has no words, phrases or tags to search for."""


@dataclass(frozen=True)
class SearchQuery:
    """A parsed search string. Every word is already analyzed (folded)."""

    terms: tuple[str, ...] = ()
    phrases: tuple[tuple[str, ...], ...] = ()
    tags: tuple[str, ...] = ()  # normalized tag keys (see `normalize_tag_name`)
    prefix: str | None = None


# The last word is matched as a prefix (search while typing) only when it is
# at least this long; shorter prefixes match most of the corpus.
MIN_PREFIX_LENGTH = 2

_CHUNK = re.compile(
    r'(?i:tag):(?:"(?P<quoted_tag>[^"]*)"?|(?P<tag>[^\s"]*))'
    r'|"(?P<phrase>[^"]*)"?'
    r'|(?P<word>[^\s"]+)',
)


def _tag_key(name: str) -> str:
    try:
        return normalize_tag_name(name)[1]
    except InvalidTagNameError:
        # Empty (ignored by the caller) or too long to exist (an unknown tag).
        return name.strip().casefold()


def parse_query(raw: str) -> SearchQuery:
    """Parse `raw` into a `SearchQuery`.

    The last bare word becomes a prefix when the string doesn't end in
    whitespace (the user is still typing it) and it has at least
    `MIN_PREFIX_LENGTH` characters.

    Raises:
        EmptySearchQueryError: If nothing searchable is left after parsing.
    """
    terms: list[str] = []
    phrases: list[tuple[str, ...]] = []
    tags: list[str] = []
    last_chunk_is_word = False
    for match in _CHUNK.finditer(raw):
        tag_name = match.group("quoted_tag") or match.group("tag")
        if match.group("quoted_tag") is not None or match.group("tag") is not None:
            last_chunk_is_word = False
            key = _tag_key(tag_name or "")
            if key and key not in tags:
                tags.append(key)
            continue
        if match.group("word") is not None:
            terms.extend(analyze(match.group("word")))
            last_chunk_is_word = True
            continue
        last_chunk_is_word = False
        words = analyze(match.group("phrase"))
        if len(words) > 1:
            phrases.append(tuple(words))
        else:
            terms.extend(words)

    prefix: str | None = None
    still_typing = last_chunk_is_word and not raw[-1].isspace()
    if still_typing and terms and len(terms[-1]) >= MIN_PREFIX_LENGTH:
        prefix = terms.pop()
    if not (terms or phrases or tags or prefix):
        raise EmptySearchQueryError(raw)
    return SearchQuery(
        terms=tuple(terms),
        phrases=tuple(phrases),
        tags=tuple(tags),
        prefix=prefix,
    )


def _lexeme(word: str) -> str:
    # `analyze` only yields \w+ tokens; quoting is defence in depth so input
    # can never turn into tsquery operators.
    return "'" + word.replace("\\", "\\\\").replace("'", "''") + "'"


def to_tsquery(query: SearchQuery) -> str | None:
    """The text part of `query` as a Postgres `to_tsquery` string.

    All terms, phrases and the prefix are ANDed. Returns None for a
    tag-only query.
    """
    parts = [_lexeme(term) for term in query.terms]
    parts += [
        "(" + " <-> ".join(_lexeme(w) for w in phrase) + ")" for phrase in query.phrases
    ]
    if query.prefix is not None:
        parts.append(_lexeme(query.prefix) + ":*")
    return " & ".join(parts) or None


def to_any_word_tsquery(query: SearchQuery) -> str | None:
    """A `to_tsquery` string matching any single word of `query`.

    Used to pick snippet blocks: a note matches only when all its words do,
    but each block shown only needs to contain one of them.
    """
    words = [*query.terms, *(w for phrase in query.phrases for w in phrase)]
    parts = [_lexeme(word) for word in dict.fromkeys(words)]
    if query.prefix is not None:
        parts.append(_lexeme(query.prefix) + ":*")
    return " | ".join(parts) or None
