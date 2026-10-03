"""Pure HTML -> note-blocks parser for the notes-import adapter.

No DB/IO dependency — takes an HTML string and returns a `ParsedNote`, so the
parsing-rule matrix can be tested cheaply with raw HTML strings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from bs4 import BeautifulSoup, NavigableString, Tag
from bs4.element import PreformattedString

if TYPE_CHECKING:
    from collections.abc import Callable

# The first <h1> is the note title; any later <h1> is a level-1 heading.
_HEADING_LEVELS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}

# Tags that never render as content (structural/metadata-only).
_IGNORED_TAGS = {
    "head",
    "meta",
    "link",
    "style",
    "script",
    "title",
    "svg",
    "noscript",
    "template",
}

# Embedded media, imported as an attachment placeholder like Evernote
# resources.
_MEDIA_TAGS = {"picture", "video", "audio", "iframe", "object", "embed", "canvas"}

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
    "en-codeblock",
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


# Upper bound on a cell's colspan/rowspan, against malformed HTML.
_MAX_TABLE_SPAN = 100

# CommonMark ordered-list numbers have at most 9 digits.
_MAX_LIST_NUMBER_DIGITS = 9


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
    skip: bool = False  # True => skipped web.clip; caller must not persist anything
    web_clip: bool = False  # the note is a web clipping (source=web.clip)


def parse_html_note(
    html: str, *, fallback_title: str, include_web_clips: bool = False
) -> ParsedNote:
    """Parse an exported HTML note into a title and ordered blocks.

    Args:
        html: The raw HTML document (or fragment) to parse.
        fallback_title: Title to use when neither an ``<h1>`` nor a
            ``meta itemprop=title`` tag is present.
        include_web_clips: Parse web clippings (``meta itemprop=source`` =
            ``web.clip``) like any other note instead of marking them
            ``skip``.
    """
    soup = BeautifulSoup(html, "html.parser")

    source_meta = soup.find("meta", attrs={"itemprop": "source"})
    web_clip = isinstance(source_meta, Tag) and source_meta.get("content") == "web.clip"
    if web_clip and not include_web_clips:
        return ParsedNote(title="", blocks=[], skip=True, web_clip=True)

    title_h1 = soup.find("h1")
    title = _resolve_title(soup, title_h1, fallback_title)

    blocks = _process_children(soup, title_h1)
    return ParsedNote(title=title, blocks=blocks, skip=False, web_clip=web_clip)


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
    if el is title_h1 or el.name in _IGNORED_TAGS:
        return []
    handler = _BLOCK_HANDLERS.get(el.name)
    if handler is not None:
        return handler(el, title_h1)
    if el.name == "table" and el.find("table") is None:
        return _process_table(el)
    if _is_attachment(el):
        # TODO: attachment support (see spec Out of Scope). The card's caption
        # (the file name) is not note content.
        return [ParsedBlock("paragraph", "Skipped block: attachment")]

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


def _process_heading(el: Tag, _title_h1: Tag | None) -> list[ParsedBlock]:
    text = _inline_text(el)
    if not text:
        return []
    return [ParsedBlock("heading", f"{'#' * _HEADING_LEVELS[el.name]} {text}")]


def _process_image(_el: Tag, _title_h1: Tag | None) -> list[ParsedBlock]:
    # TODO: image support (see spec Out of Scope)
    return [ParsedBlock("paragraph", "Skipped block: image")]


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
    return el.name in _BLOCK_TAGS or _is_attachment(el) or _has_block_child(el)


def _is_attachment(el: Tag) -> bool:
    """An attachment: embedded media, ``en-media`` or a resource card (not ``<img>``)."""
    if el.name == "en-media" or el.name in _MEDIA_TAGS:
        return True
    return el.name != "img" and el.has_attr("data-resource-hash")


def _has_block_child(el: Tag) -> bool:
    return any(isinstance(c, Tag) and _is_block(c) for c in el.children)


def _process_code_block(el: Tag, _title_h1: Tag | None = None) -> list[ParsedBlock]:
    """Render ``<pre>`` or Evernote's ``<en-codeblock>`` as a fenced code block.

    The text is kept verbatim (no Markdown escaping); ``<br>`` and block
    children (one ``<div>`` per line in ``en-codeblock``) become line breaks.
    """
    text = _preformatted_text(el).strip("\n")
    if not text.strip():
        return []
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return [ParsedBlock("code_block", f"{fence}{_code_language(el)}\n{text}\n{fence}")]


def _preformatted_text(node: Tag) -> str:
    parts: list[str] = []
    for child in node.children:
        if isinstance(child, PreformattedString):
            continue
        if isinstance(child, NavigableString):
            parts.append(str(child))
        elif isinstance(child, Tag) and child.name not in _IGNORED_TAGS:
            if child.name == "br":
                parts.append("\n")
            elif child.name in _BLOCK_TAGS:
                parts.append(_preformatted_text(child).rstrip("\n") + "\n")
            else:
                parts.append(_preformatted_text(child))
    return "".join(parts)


def _code_language(el: Tag) -> str:
    """The ``language-xxx`` class of a code block or its ``<code>``, if any."""
    for tag in (el, el.find("code")):
        if isinstance(tag, Tag):
            for cls in tag.get("class") or []:
                if cls.startswith("language-") and re.fullmatch(r"[\w+#.-]+", cls[9:]):
                    return cls[9:]
    return ""


def _process_blockquote(el: Tag, title_h1: Tag | None) -> list[ParsedBlock]:
    """Render a ``<blockquote>`` as one quote block.

    The editor's quote holds inline content only, so the inner blocks become
    lines of the quote, separated by empty quote lines.
    """
    inner = _process_children(el, title_h1)
    if not inner:
        return []
    paragraphs = [
        "\n".join(f"> {line}".rstrip() for line in block.payload.split("\n"))
        for block in inner
    ]
    return [ParsedBlock("blockquote", "\n>\n".join(paragraphs))]


def _process_table(el: Tag) -> list[ParsedBlock]:
    """Render a table as one GFM pipe table in a ``paragraph`` block.

    The editor stores its own tables the same way. The first row is the
    header. GFM has no merged cells, so a ``colspan`` cell repeats its content
    and a ``rowspan`` leaves the cells below it empty: no text is lost.
    Only tables without nested tables get here: a table holding tables is
    page layout (common in web clips) and is recursed into like a container.
    """
    rows: list[list[str]] = []
    spanned: dict[int, int] = {}  # column -> rows still covered by a rowspan
    for tr in el.find_all("tr"):
        if tr.find_parent("table") is not el:
            continue
        row: list[str] = []
        for cell in tr.find_all(["td", "th"], recursive=False):
            while spanned.get(len(row)):
                spanned[len(row)] -= 1
                row.append("")
            text = _normalize(_render_inline(cell)).replace("|", "\\|")
            rowspan = _span(cell, "rowspan")
            for _ in range(_span(cell, "colspan")):
                if rowspan > 1:
                    spanned[len(row)] = rowspan - 1
                row.append(text)
        while spanned.get(len(row)):
            spanned[len(row)] -= 1
            row.append("")
        rows.append(row)
    width = max((len(row) for row in rows), default=0)
    if width == 0:
        return []
    lines = ["| " + " | ".join(row + [""] * (width - len(row))) + " |" for row in rows]
    lines.insert(1, "| " + " | ".join(["---"] * width) + " |")
    return [ParsedBlock("paragraph", "\n".join(lines))]


def _span(cell: Tag, attr: str) -> int:
    value = cell.get(attr)
    if isinstance(value, str) and value.isdigit():
        return max(1, min(int(value), _MAX_TABLE_SPAN))
    return 1


@dataclass(slots=True)
class _ListItem:
    """One list item: its own text, its sub-items and how its marker renders."""

    text: str
    children: list[_ListItem] = field(default_factory=list)
    number: int | None = None  # set for items of an <ol>
    box: str = ""  # "[x] " / "[ ] " for checklist items
    synthetic: bool = False  # empty parent for a sub-list with no <li> before it

    @property
    def marker(self) -> str:
        return f"{self.number}. " if self.number is not None else f"- {self.box}"


def _process_list(el: Tag, _title_h1: Tag | None = None) -> list[ParsedBlock]:
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
    todo = _is_todo_list(el)
    items: list[_ListItem] = []
    for child in list(el.children):
        if not isinstance(child, Tag):
            continue
        if child.name in ("ul", "ol"):
            nested = _list_items(child)
            if items:
                items[-1].children.extend(nested)
            elif nested:
                # No <li> to attach to: an unnumbered empty parent holds it.
                items.append(_ListItem("", nested, synthetic=True))
            continue
        # Sub-lists are detached so the item's own text excludes them.
        sub_lists = [
            sub.extract()
            for sub in child.find_all(["ul", "ol"])
            if sub.find_parent(["ul", "ol"]) is el
        ]
        item = _ListItem(
            _finish_block_text(_render_inline(child)),
            [item for sub in sub_lists for item in _list_items(sub)],
        )
        if todo and child.name == "li":
            item.box = "[x] " if child.get("data-checked") == "true" else "[ ] "
        items.append(item)

    # Empty items (Evernote often leaves a trailing <li><br></li>) are dropped
    # once sibling sub-lists have attached to them; an empty parent is kept.
    items = [item for item in items if item.text or item.children]
    if el.name == "ol":
        numbered = [item for item in items if not item.synthetic]
        for number, item in enumerate(numbered, start=_list_start(el)):
            item.number = number
    return items


def _list_start(el: Tag) -> int:
    """First number of an ``<ol>``: its ``start`` attribute, else 1.

    Each list counts only its own items, so nested lists restart.
    """
    start = el.get("start")
    max_digits = _MAX_LIST_NUMBER_DIGITS
    if isinstance(start, str) and start.isdigit() and len(start) <= max_digits:
        return int(start)
    return 1


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
    if _is_attachment(node):
        return " "
    if markdown and node.name == "code":
        return _code_span(_normalize(_render_inline(node, markdown=False)))
    inner = _render_children(node, markdown=markdown)
    marker = _FORMAT_MARKERS.get(node.name) if markdown else None
    if marker:
        return _wrap(marker, inner)
    if markdown and node.name == "a" and node.get("href") and inner.strip():
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


# Elements with their own block rendering, by tag name.
_BLOCK_HANDLERS: dict[str, Callable[[Tag, Tag | None], list[ParsedBlock]]] = {
    **dict.fromkeys(_HEADING_LEVELS, _process_heading),
    "ul": _process_list,
    "ol": _process_list,
    "pre": _process_code_block,
    "en-codeblock": _process_code_block,
    "blockquote": _process_blockquote,
    "hr": lambda _el, _title_h1: [],
    "img": _process_image,
}
