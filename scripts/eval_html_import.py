# A report script: its output is printed.
# ruff: noqa: T201
"""Evaluate the HTML notes importer against a local Evernote HTML export.

For every note the script compares two renderings produced by the same
independent reference walker:

* the *reference*: the original exported HTML;
* the *candidate*: the importer's Markdown payloads, each converted back to HTML
  with markdown-it (the same per-node parse the editor does).

Each rendering is a list of lines such as ``"  - **bold** text"`` (indent =
nesting depth). Differences are classified (nesting, numbering, checkbox,
formatting, empty bullet, missing/extra content) and a word-level check reports
words present in the HTML but absent from the import. Links are compared by
text only and attachments are compared as placeholders.

The export holds personal notes, so this is a local tool and not part of
``make check``. Usage::

    python scripts/eval_html_import.py ~/Documents/notes
    python scripts/eval_html_import.py ~/Documents/notes --sample 95 --seed 1 -v
    python scripts/eval_html_import.py ~/Documents/notes --include-web-clips
"""

from __future__ import annotations

import argparse
import collections
import difflib
import random
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from bs4 import BeautifulSoup, NavigableString, Tag
from markdown_it import MarkdownIt
from mdit_py_plugins.tasklists import tasklists_plugin

from assistant.adapters.html_parser import parse_html_note

if TYPE_CHECKING:
    from collections.abc import Iterable
from assistant.adapters.plugins.html_file import HTMLFileImportSource

_SKIP = {
    "style",
    "script",
    "icons",
    "svg",
    "head",
    "meta",
    "note-attributes",
    "title",
    "hr",
}
_BLOCK = {
    "div", "p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "table", "tr",
    "td", "th", "pre", "blockquote", "img", "en-media", "section", "tbody", "thead",
    "figure", "iframe", "video", "picture", "article", "header", "footer", "main",
    "aside", "nav", "dl", "dt", "dd", "form", "center",
}  # fmt: skip
_ATTACHMENT = "[ATTACHMENT]"
_PLACEHOLDERS = {
    "Skipped block: attachment",
    "Skipped block: image",
    "Skipped block: table",
}
_MEDIA = {"img", "en-media", "figure", "picture", "video", "iframe"}

_EMPTY_ITEM_RE = re.compile(r"(?m)^( *(?:[-*]|\d+\.)(?: \[[ x]\])?) *$")
_md = MarkdownIt("commonmark").enable(["table", "strikethrough"]).use(tasklists_plugin)


# --- Reference walker -------------------------------------------------------


def _is_attachment(el: Tag) -> bool:
    return el.name in _MEDIA or el.has_attr("data-resource-hash")


def _has_block(e: Tag) -> bool:
    """Whether ``e`` is, or wraps, a block (web clips wrap blocks in spans)."""
    if e.name in _BLOCK or _is_attachment(e):
        return True
    return e.find(lambda t: t.name in _BLOCK or _is_attachment(t)) is not None


def _wrap(marker: str, inner: str) -> str:
    core = inner.strip()
    if not core:
        return inner
    lead = inner[: len(inner) - len(inner.lstrip())]
    trail = inner[len(inner.rstrip()) :]
    return f"{lead}{marker}{core}{marker}{trail}"


def _inline(e: object) -> str:  # noqa: PLR0911
    if isinstance(e, NavigableString):
        return str(e)
    if not isinstance(e, Tag) or e.name in _SKIP:
        return ""
    if e.name == "br":
        return " "
    if e.name == "input":
        return ""
    inner = "".join(_inline(c) for c in e.children)
    if e.name in ("b", "strong"):
        return _wrap("**", inner)
    if e.name in ("i", "em"):
        return _wrap("*", inner)
    if e.name in ("s", "strike", "del"):
        return _wrap("~~", inner)
    if e.name == "code":
        return _wrap("`", inner)
    if _has_block(e):
        return f" {inner} "
    return inner


def _clean(text: str) -> str:
    return " ".join(text.replace("\u200b", " ").split())


@dataclass
class _Walker:
    candidate: bool
    out: list[str] = field(default_factory=list)

    def emit(self, depth: int, prefix: str, text: str) -> None:
        text = _clean(text)
        if text in _PLACEHOLDERS:
            text = _ATTACHMENT
        if text or (self.candidate and prefix):
            self.out.append("  " * depth + prefix + text)

    def walk(self, el: Tag, depth: int = 0) -> None:
        for c in el.children:
            if isinstance(c, NavigableString):
                if c.strip():
                    self.emit(depth, "", str(c))
                continue
            if isinstance(c, Tag):
                self.node(c, depth)

    def node(self, c: Tag, depth: int) -> None:  # noqa: PLR0911, PLR0912
        n = c.name
        if n in _SKIP:
            return
        if _is_attachment(c):
            self.out.append("  " * depth + _ATTACHMENT)
            return
        if n in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.emit(depth, "#" * int(n[1]) + " ", _inline(c))
            return
        if n in ("ul", "ol"):
            self.list(c, depth)
            return
        if n == "table" and c.find("table") is not None:
            self.walk(c, depth)  # layout table: cells are containers
            return
        if n in ("tr", "td", "th", "tbody", "thead", "tfoot"):
            self.walk(c, depth)
            return
        if n == "table":
            for tr in c.find_all("tr"):
                cells = [
                    _clean(_inline(td))
                    for td in tr.find_all(["td", "th"], recursive=False)
                ]
                self.out.append("  " * depth + "| " + " | ".join(cells) + " |")
            return
        if n == "pre":
            for br in c.find_all("br"):
                br.replace_with("\n")
            self.out.append("  " * depth + "```" + c.get_text().strip("\n") + "```")
            return
        if n == "en-codeblock":
            lines = "\n".join(d.get_text() for d in c.find_all("div", recursive=False))
            self.out.append("  " * depth + "```" + lines.strip("\n") + "```")
            return
        legacy = c.find("input", class_="en-todo", recursive=False)
        if legacy is not None:
            box = "[x] " if legacy.get("checked") in ("true", "checked", "") else "[ ] "
            self.emit(depth, "- " + box, _inline(c))
            return
        kids = [k for k in c.children if isinstance(k, Tag) and k.name not in _SKIP]
        if any(_has_block(k) for k in kids):
            self.walk(c, depth)
            return
        self.emit(depth, "", _inline(c))

    def list(self, c: Tag, depth: int) -> None:
        ordered = c.name == "ol"
        todo = "en-todolist" in (c.get("class") or [])
        start = c.get("start")
        k = int(start) if isinstance(start, str) and start.isdigit() else 1
        for x in c.children:
            if not isinstance(x, Tag):
                continue
            if x.name in ("ul", "ol"):
                self.list(x, depth + 1)
                continue
            if x.name != "li":
                continue
            box = ""
            if todo:
                box = "[x] " if x.get("data-checked") == "true" else "[ ] "
            else:
                task = x.find("input", class_="task-list-item-checkbox")
                if task is not None:
                    box = "[x] " if task.has_attr("checked") else "[ ] "
            subs = [y for y in x.find_all(["ul", "ol"]) if y.find_parent("li") is x]
            for sub in subs:
                sub.extract()
            own = _inline(x)
            marker = f"{k}. " if ordered else "- "
            if _clean(own) or not subs:
                self.emit(depth, marker + box, own)
            k += 1
            for sub in subs:
                self.list(sub, depth + 1)


def reference_lines(html: str) -> tuple[str | None, list[str]]:
    """Render the original export HTML; returns (title, body lines)."""
    soup = BeautifulSoup(html, "html.parser")
    root = soup.find("en-note") or soup.body or soup
    h1 = soup.find("h1")
    title = _clean(h1.get_text(" ")) if isinstance(h1, Tag) else None
    if isinstance(h1, Tag):
        h1.decompose()
    w = _Walker(candidate=False)
    if isinstance(root, Tag):
        w.walk(root)
    return title, w.out


def candidate_lines(payloads: Iterable[str]) -> list[str]:
    """Render the importer's payloads, one markdown-it parse per node."""
    w = _Walker(candidate=True)
    for payload in payloads:
        # markdown-it reads an empty nested item ("  -") as a setext heading
        # underline; BlockNote does not. Give it invisible content.
        markdown = _EMPTY_ITEM_RE.sub("\\1 \u200b", payload)
        w.walk(BeautifulSoup(_md.render(markdown), "html.parser"))
    return w.out


# --- Comparison -------------------------------------------------------------

_LINE_RE = re.compile(
    r"^(?P<indent> *)(?P<marker>(?:#+ |- |\d+\. |\| )?)"
    r"(?P<box>(?:\[[ x]\] )?)(?P<text>.*)$",
    re.DOTALL,
)
_TOKEN_RE = re.compile(r"\w+")


@dataclass(frozen=True)
class _Line:
    depth: int
    marker: str
    box: str
    text: str

    @property
    def plain(self) -> str:
        return _clean(re.sub(r"[*~`]", "", self.text))

    @property
    def kind(self) -> str:
        if re.match(r"\d+\. ", self.marker):
            return "N. "
        return self.marker


def _split(line: str) -> _Line:
    m = _LINE_RE.match(line)
    assert m is not None
    return _Line(len(m["indent"]) // 2, m["marker"], m["box"], m["text"])


def _classify(ref: _Line, cand: _Line) -> str:
    if ref.kind != cand.kind:
        return "wrong_block_type"
    if ref.depth != cand.depth:
        return "nesting"
    if ref.box != cand.box:
        return "checkbox"
    if ref.marker != cand.marker:
        return "numbering"
    if ref.text != cand.text:
        return "formatting"
    return "other"


def compare(ref_lines: list[str], cand_lines: list[str]) -> collections.Counter[str]:
    """Classify the line differences between reference and candidate."""
    issues: collections.Counter[str] = collections.Counter()
    for line in cand_lines:
        if _split(line).marker and not _split(line).text.strip():
            issues["empty_bullet"] += 1
    cand_lines = [
        x for x in cand_lines if not (_split(x).marker and not _split(x).text.strip())
    ]
    sm = difflib.SequenceMatcher(a=ref_lines, b=cand_lines, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        refs = [_split(x) for x in ref_lines[i1:i2]]
        cands = [_split(x) for x in cand_lines[j1:j2]]
        by_plain: dict[str, list[_Line]] = collections.defaultdict(list)
        for c in cands:
            by_plain[c.plain].append(c)
        for r in refs:
            match = by_plain.get(r.plain)
            if match:
                issues[_classify(r, match.pop(0))] += 1
            else:
                issues["missing_line"] += 1
        issues["extra_line"] += sum(len(v) for v in by_plain.values())
    return issues


def _tokens(lines: Iterable[str]) -> collections.Counter[str]:
    return collections.Counter(
        t for line in lines for t in _TOKEN_RE.findall(_split(line).text.lower())
    )


@dataclass
class NoteResult:
    doc: str
    issues: collections.Counter[str]
    missing_words: list[str]
    extra_words: list[str]
    diff: list[str]


def evaluate(root: Path, doc: str, *, include_web_clips: bool) -> NoteResult | None:
    """Evaluate one note; returns None for skipped web clips."""
    html = (root / doc).read_text(encoding="utf-8")
    parsed = parse_html_note(
        html, fallback_title=Path(doc).stem, include_web_clips=include_web_clips
    )
    if parsed.skip:
        return None
    title, ref = reference_lines(html)
    cand = candidate_lines(b.payload for b in parsed.blocks)
    issues = compare(ref, cand)
    if title is not None and _clean(title) != _clean(parsed.title):
        issues["title"] += 1
    missing = _tokens(ref) - _tokens(cand)
    if missing:
        issues["notes_missing_words"] = 1
    extra = _tokens(cand) - _tokens(ref)
    if extra:
        issues["notes_extra_words"] = 1
    diff = list(difflib.unified_diff(ref, cand, "html", "import", n=1, lineterm=""))
    return NoteResult(doc, issues, sorted(missing), sorted(extra), diff)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("root", type=Path, help="Root directory of the HTML export")
    ap.add_argument("--sample", type=int, help="Evaluate a random sample of N notes")
    ap.add_argument("--seed", type=int, default=0, help="Random seed for --sample")
    ap.add_argument(
        "--docs", type=Path, help="File with one export-relative note path per line"
    )
    ap.add_argument(
        "--include-web-clips", action="store_true", help="Import web clips too"
    )
    ap.add_argument(
        "--only-web-clips", action="store_true", help="Evaluate web clips only"
    )
    ap.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print the diff of every note with issues",
    )
    args = ap.parse_args(argv)

    source = HTMLFileImportSource(args.root)
    docs = list(source.list_documents())
    if args.docs:
        docs = [d for d in args.docs.read_text().splitlines() if d.strip()]
    if args.only_web_clips:
        docs = [
            d
            for d in docs
            if 'content="web.clip"' in (args.root / d).read_text(encoding="utf-8")
        ]
    if args.sample:
        docs = random.Random(args.seed).sample(docs, min(args.sample, len(docs)))

    totals: collections.Counter[str] = collections.Counter()
    notes_with: collections.Counter[str] = collections.Counter()
    evaluated = skipped = clean = 0
    for doc in docs:
        result = evaluate(
            args.root,
            doc,
            include_web_clips=args.include_web_clips or args.only_web_clips,
        )
        if result is None:
            skipped += 1
            continue
        evaluated += 1
        totals.update(result.issues)
        notes_with.update(result.issues.keys())
        if not result.issues:
            clean += 1
        elif args.verbose:
            print(f"\n=== {doc} {dict(result.issues)}")
            if result.missing_words:
                print("    missing words:", " ".join(result.missing_words[:20]))
            if result.extra_words:
                print("    extra words:", " ".join(result.extra_words[:20]))
            for line in result.diff[2:]:
                print("    " + line[:160])

    print(
        f"\nnotes: {len(docs)}  evaluated: {evaluated}"
        f"  skipped web clips: {skipped}  clean: {clean}"
    )
    for issue in sorted(notes_with):
        print(f"  {issue:22} notes={notes_with[issue]:4}  occurrences={totals[issue]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
