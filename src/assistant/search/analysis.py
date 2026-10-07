"""Text analysis shared by indexing and querying.

Tokenization happens here, in Python, rather than in Postgres: the index
stores `" ".join(analyze(text))`, so Postgres' `simple` parser only sees
clean words, and queries go through the very same function. Index and
query can therefore never tokenize differently.

Analysis is: Unicode NFKD, drop combining marks (accent folding), casefold,
split on `\\w+`. There is no stemming (notes mix languages).
"""

from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING

from markdown_it import MarkdownIt

if TYPE_CHECKING:
    from markdown_it.token import Token

# Bump whenever anything in this module changes what gets indexed, then run
# `python -m assistant.cli.reindex_search --stale-only`.
SEARCH_INDEX_VERSION = 1

_WORD = re.compile(r"\w+")


def fold(text: str) -> str:
    """Accent-fold and casefold `text` (``"Perché"`` -> ``"perche"``)."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.casefold()


def analyze(text: str) -> list[str]:
    """Split `text` into folded search tokens."""
    return _WORD.findall(fold(text))


def tokens_with_offsets(text: str) -> list[tuple[str, int, int]]:
    """Tokenize `text`, keeping each token's span in the original string.

    Returns (folded token, start, end) triples, so snippet highlighting can
    match folded query terms while showing the original characters.
    """
    return [(fold(m.group()), m.start(), m.end()) for m in _WORD.finditer(text)]


_MARKDOWN = MarkdownIt("commonmark")


def _inline_text(children: list[Token]) -> list[str]:
    parts: list[str] = []
    for child in children:
        if child.type in ("text", "code_inline"):
            parts.append(child.content)
        elif child.type in ("softbreak", "hardbreak"):
            parts.append(" ")
        elif child.type == "image" and child.children:
            parts.extend(_inline_text(child.children))
        # Link markers, emphasis markers and inline HTML carry no text.
    return parts


def markdown_to_plain(payload: str) -> str:
    """The human-readable text of a markdown block.

    Drops markdown syntax, URLs and HTML; keeps link text, image alt text
    and code. Used both for indexing and for building snippets.
    """
    blocks: list[str] = []
    for token in _MARKDOWN.parse(payload):
        if token.type == "inline" and token.children is not None:
            blocks.append("".join(_inline_text(token.children)))
        elif token.type in ("code_block", "fence"):
            blocks.append(token.content.rstrip("\n"))
    return " ".join(block for block in blocks if block)
