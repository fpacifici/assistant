"""Pure HTML -> note-blocks parser for the notes-import adapter.

No DB/IO dependency — takes an HTML string and returns a `ParsedNote`, so the
parsing-rule matrix can be tested cheaply with raw HTML strings.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from bs4 import BeautifulSoup, NavigableString, Tag
from bs4.element import PreformattedString

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
    "input",
}

# Tags that always start a new block. Any other tag is a block only if it wraps
# a block (e.g. a <span> around <div>s); otherwise its content is inline text.
_BLOCK_TAGS = {
    "html",
    "body",
    "en-note",
    "div",
    "p",
    "section",
    "article",
    "header",
    "footer",
    "main",
    "aside",
    "nav",
    "center",
    "address",
    "form",
    "fieldset",
    "details",
    "summary",
    "figure",
    "figcaption",
    "blockquote",
    "pre",
    "hr",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "ul",
    "ol",
    "li",
    "dl",
    "dt",
    "dd",
    "table",
    "thead",
    "tbody",
    "tfoot",
    "tr",
    "td",
    "th",
    "img",
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

    blocks = _process_children(soup, title_h1)
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

    if _has_block_child(el):
        return _process_children(el, title_h1)

    text = _inline_text(el)
    if not text:
        return []
    return [ParsedBlock("paragraph", text)]


def _process_children(el: Tag, title_h1: Tag | None) -> list[ParsedBlock]:
    """Turn a container's children into blocks, keeping loose inline content.

    Consecutive inline children (text nodes and inline tags) are collected into
    one paragraph, flushed whenever a block child starts, so text sitting next
    to block-level siblings is not lost and document order is preserved.
    """
    blocks: list[ParsedBlock] = []
    run: list[object] = []

    def flush() -> None:
        text = _normalize("".join(_render_inline(n) for n in run))
        run.clear()
        if text:
            blocks.append(ParsedBlock("paragraph", text))

    for child in el.children:
        if isinstance(child, Tag) and (child is title_h1 or _is_block(child)):
            flush()
            blocks.extend(_process_node(child, title_h1))
        else:
            run.append(child)
    flush()
    return blocks


def _is_block(el: Tag) -> bool:
    if el.name in _IGNORED_TAGS:
        return False
    return el.name in _BLOCK_TAGS or _has_block_child(el)


def _has_block_child(el: Tag) -> bool:
    return any(isinstance(c, Tag) and _is_block(c) for c in el.children)


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


def _render_inline(node: object) -> str:  # noqa: PLR0911
    if isinstance(node, PreformattedString):  # comments, doctypes, CDATA...
        return ""
    if isinstance(node, NavigableString):
        return str(node)
    if not isinstance(node, Tag):
        return ""
    if node.name in _IGNORED_TAGS:
        return ""
    if node.name == "br":
        return " "
    inner = "".join(_render_inline(c) for c in node.children)
    if node.name == "a" and node.get("href"):
        return f"[{inner}]({node['href']})"
    if _is_block(node):
        # Block boundaries inside inline content (e.g. several div.para in one
        # <li>) separate words, like <br>; _normalize collapses the spaces.
        return f" {inner} "
    return inner


def _normalize(text: str) -> str:
    return " ".join(text.split())
