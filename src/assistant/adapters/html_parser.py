"""Pure HTML -> note-blocks parser for the notes-import adapter.

No DB/IO dependency — takes an HTML string and returns a `ParsedNote`, so the
parsing-rule matrix can be tested cheaply with raw HTML strings.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from bs4 import BeautifulSoup, NavigableString, Tag

_HEADING_LEVELS = {"h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}

# Tags that never render as content (structural/metadata-only).
_IGNORED_TAGS = {"head", "meta", "link", "style", "script", "title"}

# Formatting/inline tags that fold into an ancestor block's text rather than
# ever becoming a block of their own.
_INLINE_TAGS = {
    "a",
    "b",
    "strong",
    "i",
    "em",
    "u",
    "span",
    "s",
    "strike",
    "sub",
    "sup",
    "code",
    "font",
    "small",
    "mark",
    "abbr",
    "cite",
    "q",
    "time",
    "wbr",
    "br",
}


@dataclass(frozen=True, slots=True)
class ParsedBlock:
    """One storable note block, ready to become a MarkdownNode."""

    block_type: str  # a MarkdownBlockType.value
    payload: str


@dataclass(frozen=True, slots=True)
class ParsedNote:
    """The result of parsing one HTML note."""

    title: str
    blocks: list[ParsedBlock] = field(default_factory=list)
    skip: bool = False  # True => web.clip; caller must not persist anything


def parse_html_note(html: str, *, fallback_title: str) -> ParsedNote:
    """Parse an exported HTML note into a title and ordered blocks.

    Args:
        html: The raw HTML document (or fragment) to parse.
        fallback_title: Title to use when neither an ``<h1>`` nor a
            ``meta itemprop=title`` tag is present.
    """
    soup = BeautifulSoup(html, "html.parser")

    source_meta = soup.find("meta", attrs={"itemprop": "source"})
    if isinstance(source_meta, Tag) and source_meta.get("content") == "web.clip":
        return ParsedNote(title="", blocks=[], skip=True)

    title_h1 = soup.find("h1")
    title = _resolve_title(soup, title_h1, fallback_title)

    blocks: list[ParsedBlock] = []
    for child in soup.find_all(recursive=False):
        blocks.extend(_process_node(child, title_h1))

    return ParsedNote(title=title, blocks=blocks, skip=False)


def _resolve_title(soup: BeautifulSoup, title_h1: Tag | None, fallback_title: str) -> str:
    if title_h1 is not None:
        return _inline_text(title_h1)
    title_meta = soup.find("meta", attrs={"itemprop": "title"})
    if isinstance(title_meta, Tag):
        content = title_meta.get("content")
        if isinstance(content, str) and content:
            return content
    return fallback_title


def _process_node(el: Tag, title_h1: Tag | None) -> list[ParsedBlock]:  # noqa: PLR0911
    if el is title_h1:
        return []

    name = el.name
    if name in _IGNORED_TAGS:
        return []
    if name in _HEADING_LEVELS:
        level = _HEADING_LEVELS[name]
        return [ParsedBlock("heading", f"{'#' * level} {_inline_text(el)}")]
    if name in ("ul", "ol"):
        return _process_list(el, ordered=name == "ol")
    if name == "table":
        # TODO: table support (see spec Out of Scope)
        return [ParsedBlock("paragraph", "Skipped block: table")]
    if name == "img":
        # TODO: image support (see spec Out of Scope)
        return [ParsedBlock("paragraph", "Skipped block: image")]

    child_tags = [c for c in el.children if isinstance(c, Tag)]
    has_block_child = any(c.name not in _INLINE_TAGS for c in child_tags)
    if has_block_child:
        blocks: list[ParsedBlock] = []
        for child in child_tags:
            blocks.extend(_process_node(child, title_h1))
        return blocks

    text = _inline_text(el)
    if not text:
        return []
    return [ParsedBlock("paragraph", text)]


def _process_list(el: Tag, *, ordered: bool) -> list[ParsedBlock]:
    # TODO: nested list support (see spec Out of Scope) — nested <li>s are
    # flattened to top-level list_item blocks via this recursive find_all.
    blocks: list[ParsedBlock] = []
    counter = 1
    for li in el.find_all("li"):
        text = _li_text(li)
        marker = f"{counter}. " if ordered else "- "
        blocks.append(ParsedBlock("list_item", marker + text))
        if ordered:
            counter += 1
    return blocks


def _li_text(li: Tag) -> str:
    parts = []
    for child in li.children:
        if isinstance(child, Tag) and child.name in ("ul", "ol"):
            continue
        parts.append(_render_inline(child))
    return _normalize("".join(parts))


def _inline_text(el: Tag) -> str:
    return _normalize(_render_inline(el))


def _render_inline(node: object) -> str:
    if isinstance(node, NavigableString):
        return str(node)
    if not isinstance(node, Tag):
        return ""
    if node.name in _IGNORED_TAGS:
        return ""
    if node.name == "br":
        return " "
    if node.name == "a" and node.get("href"):
        inner = "".join(_render_inline(c) for c in node.children)
        return f"[{inner}]({node['href']})"
    return "".join(_render_inline(c) for c in node.children)


def _normalize(text: str) -> str:
    return " ".join(text.split())
