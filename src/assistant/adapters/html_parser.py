"""Pure HTML -> note-blocks parser for the notes-import adapter.

No DB/IO dependency — takes an HTML string and returns a `ParsedNote`, so the
parsing-rule matrix can be tested cheaply with raw HTML strings.
"""

from __future__ import annotations

import re
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


# Inline formatting tags and the Markdown marker wrapping their content.
_FORMAT_MARKERS = {
    "b": "**",
    "strong": "**",
    "i": "*",
    "em": "*",
    "s": "~~",
    "strike": "~~",
    "del": "~~",
}

# Characters that would otherwise be read as inline Markdown in plain text.
_INLINE_ESCAPE_RE = re.compile(r"([\\`*_\[\]~])")

# "<" starting something tag-like (``vector<int>``). The editor's Markdown
# parser swallows it as raw HTML and mishandles the ``\<`` escape, so a
# zero-width space is inserted after the "<" to keep the text visible.
_TAG_START_RE = re.compile(r"<(?=[A-Za-z/!?])")

# Line starts that would otherwise turn a paragraph into a heading, quote,
# list item or thematic break.
_BLOCK_START_RE = re.compile(r"^(?:[#>+-]|(\d+)([.)])(?=\s|$))")


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
        return _plain_text(title_h1)
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
        return _process_list(el)
    if name == "table":
        # TODO: table support (see spec Out of Scope)
        return [ParsedBlock("paragraph", "Skipped block: table")]
    if name == "img":
        # TODO: image support (see spec Out of Scope)
        return [ParsedBlock("paragraph", "Skipped block: image")]

    if _has_block_child(el):
        return _process_children(el, title_h1)

    legacy_todo = _legacy_todo_input(el)
    if legacy_todo is not None:
        box = "[x]" if legacy_todo.get("checked") == "true" else "[ ]"
        return [ParsedBlock("list_item", f"- {box} {_inline_text(el)}")]

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
        text = _finish_block_text("".join(_render_inline(n) for n in run))
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


@dataclass(slots=True)
class _ListItem:
    """One list item: its marker (``- ``, ``2. ``, ``- [x] ``), text and sub-items."""

    marker: str
    text: str
    children: list[_ListItem] = field(default_factory=list)


def _process_list(el: Tag) -> list[ParsedBlock]:
    """Emit one ``list_item`` block per top-level item of ``el``.

    Each block's payload is the item line followed by its sub-items as
    indented Markdown, which is how the editor stores a list block with
    nested children (one node per top-level block).
    """
    return [
        ParsedBlock("list_item", "\n".join(_render_list_item(item, indent="")))
        for item in _list_items(el)
    ]


def _list_items(el: Tag) -> list[_ListItem]:
    """Build the item tree of the ``<ul>``/``<ol>`` ``el``.

    Evernote nests a sub-list as a *sibling* ``<ul>`` following the ``<li>``
    it belongs to; standard HTML nests it inside the ``<li>``. Both attach
    the sub-list's items as children of that ``<li>``.
    """
    ordered = el.name == "ol"
    todo = _is_todo_list(el)
    items: list[_ListItem] = []
    counter = 1
    for child in list(el.children):
        if not isinstance(child, Tag):
            continue
        if child.name in ("ul", "ol"):
            nested = _list_items(child)
            if items:
                items[-1].children.extend(nested)
            else:
                items.append(_ListItem("- ", "", nested))
            continue
        marker = f"{counter}. " if ordered else "- "
        if todo and child.name == "li":
            marker += "[x] " if child.get("data-checked") == "true" else "[ ] "
        # Sub-lists are detached so the item's own text excludes them.
        sub_lists = [
            sub.extract()
            for sub in child.find_all(["ul", "ol"])
            if sub.find_parent(["ul", "ol"]) is el
        ]
        children = [item for sub in sub_lists for item in _list_items(sub)]
        text = _finish_block_text(_render_inline(child))
        items.append(_ListItem(marker, text, children))
        counter += 1
    return items


def _render_list_item(item: _ListItem, *, indent: str) -> list[str]:
    lines = [f"{indent}{item.marker}{item.text}"]
    # Children sit at the parent's content column: 2 spaces under "- " and
    # "- [ ] " (what BlockNote writes), the marker width under "N. ".
    child_indent = indent + " " * (2 if item.marker.startswith("-") else len(item.marker))
    for child in item.children:
        lines.extend(_render_list_item(child, indent=child_indent))
    return lines


def _is_todo_list(el: Tag | None) -> bool:
    # Evernote puts a hidden input.list-bullet-todo in every <li>; only items
    # directly in a ul.en-todolist are checklist items.
    return el is not None and el.name == "ul" and "en-todolist" in (el.get("class") or [])


def _legacy_todo_input(el: Tag) -> Tag | None:
    """Return the ``input.en-todo`` starting ``el``, if any (older ENML checkbox).

    Its ``checked`` attribute is ``"true"`` or ``"false"``, so presence alone
    does not mean checked.
    """
    for child in el.children:
        if isinstance(child, NavigableString) and not child.strip():
            continue
        if (
            isinstance(child, Tag)
            and child.name == "input"
            and "en-todo" in (child.get("class") or [])
        ):
            return child
        return None
    return None


def _inline_text(el: Tag) -> str:
    """Render ``el``'s content as one line of inline Markdown."""
    return _finish_block_text(_render_inline(el))


def _plain_text(el: Tag) -> str:
    """Render ``el``'s content as plain text (no Markdown markers or escapes)."""
    return _normalize(_render_inline(el, markdown=False))


def _finish_block_text(text: str) -> str:
    """Normalize whitespace and escape a leading block-level Markdown marker."""
    text = _normalize(text)
    return _BLOCK_START_RE.sub(
        lambda m: f"{m[1]}\\{m[2]}" if m[1] else f"\\{m[0]}", text, count=1
    )


def _escape_markdown(text: str) -> str:
    return _TAG_START_RE.sub("<\u200b", _INLINE_ESCAPE_RE.sub(r"\\\1", text))


def _render_inline(node: object, *, markdown: bool = True) -> str:  # noqa: PLR0911
    if isinstance(node, PreformattedString):  # comments, doctypes, CDATA...
        return ""
    if isinstance(node, NavigableString):
        return _escape_markdown(str(node)) if markdown else str(node)
    if not isinstance(node, Tag):
        return ""
    if node.name in _IGNORED_TAGS:
        return ""
    if node.name == "br":
        return " "
    if markdown and node.name == "code":
        return _code_span(_normalize(_render_inline(node, markdown=False)))
    inner = _render_children(node, markdown=markdown)
    marker = _FORMAT_MARKERS.get(node.name) if markdown else None
    if marker:
        return _wrap(marker, inner)
    if markdown and node.name == "a" and node.get("href"):
        return f"[{inner}]({node['href']})"
    if _is_block(node):
        # Block boundaries inside inline content (e.g. several div.para in one
        # <li>) separate words, like <br>; _normalize collapses the spaces.
        return f" {inner} "
    return inner


def _render_children(node: Tag, *, markdown: bool) -> str:
    """Render ``node``'s children, merging adjacent same-format siblings.

    ``<b>a</b><b>b</b>`` becomes ``**ab**`` rather than ``**a****b**``, which
    Markdown would not read back as two bold runs.
    """
    parts: list[str] = []
    children = list(node.children)
    i = 0
    while i < len(children):
        marker = _marker_of(children[i]) if markdown else None
        end = i + 1
        if marker is not None:
            while end < len(children) and _marker_of(children[end]) == marker:
                end += 1
        if end - i == 1:
            parts.append(_render_inline(children[i], markdown=markdown))
        else:
            group = [t for t in children[i:end] if isinstance(t, Tag)]
            inner = "".join(_render_children(t, markdown=markdown) for t in group)
            parts.append(_wrap(marker or "", inner))
        i = end
    return "".join(parts)


def _marker_of(node: object) -> str | None:
    return _FORMAT_MARKERS.get(node.name) if isinstance(node, Tag) else None


def _wrap(marker: str, inner: str) -> str:
    """Wrap ``inner`` in ``marker``, keeping surrounding whitespace outside.

    Markdown does not read ``** bold **`` as emphasis, and an empty or
    whitespace-only run must not produce bare markers.
    """
    core = inner.strip()
    if not core:
        return inner
    lead = inner[: len(inner) - len(inner.lstrip())]
    trail = inner[len(inner.rstrip()) :]
    return f"{lead}{marker}{core}{marker}{trail}"


def _code_span(text: str) -> str:
    if not text:
        return ""
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * (longest + 1)
    pad = " " if text.startswith("`") or text.endswith("`") else ""
    return f"{fence}{pad}{text}{pad}{fence}"


def _normalize(text: str) -> str:
    return " ".join(text.split())
