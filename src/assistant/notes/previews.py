"""Note previews — a short plain-text excerpt of a note's first blocks.

Note lists show a couple of lines of each note under its title. The preview
is built from the note's first text/markdown nodes (in position order) with
the markdown syntax stripped, whitespace collapsed and the result truncated
to `PREVIEW_MAX_CHARS`.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from assistant.models.schema import Node, NodeType

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence

    from sqlalchemy.orm import Session

PREVIEW_MAX_CHARS = 200
# Nodes read per note. Blocks are usually short, so this is enough to fill
# a preview without loading whole notes.
PREVIEW_NODE_LIMIT = 10

_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_LINE_PREFIX = re.compile(
    r"^\s*(?:#{1,6}\s+|>\s?|[-*+]\s+(?:\[[ xX]\]\s+)?|\d+[.)]\s+|```\w*)",
    re.MULTILINE,
)
_EMPHASIS = re.compile(r"(\*\*|__|~~|[*`])")
_HTML_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")


def markdown_to_plain_text(markdown: str) -> str:
    """Strip common markdown syntax from `markdown`, collapsing whitespace.

    Lossy by design: it only needs to read well in a one-paragraph preview.
    """
    text = _IMAGE.sub(r"\1", markdown)
    text = _LINK.sub(r"\1", text)
    text = _LINE_PREFIX.sub("", text)
    text = _HTML_TAG.sub("", text)
    text = _EMPHASIS.sub("", text)
    text = text.replace("\\", "")
    return _WHITESPACE.sub(" ", text).strip()


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(" ", 1)[0] or text[:max_chars]
    return cut.rstrip() + "…"


def note_previews(
    session: Session,
    note_ids: Sequence[uuid.UUID],
    *,
    max_chars: int = PREVIEW_MAX_CHARS,
) -> dict[uuid.UUID, str]:
    """Return a plain-text preview for each of `note_ids`.

    Does not check note access — callers pass ids of notes they have
    already loaded through an access-checked path. Notes without any text
    content are absent from the result.
    """
    if not note_ids:
        return {}
    rank = (
        func.row_number()
        .over(partition_by=Node.note_id, order_by=Node.position)
        .label("rank")
    )
    ranked = (
        select(Node.note_id, Node.payload, rank)
        .where(
            Node.note_id.in_(note_ids),
            Node.node_type.in_([NodeType.TEXT.value, NodeType.MARKDOWN.value]),
            Node.payload != "",
        )
        .subquery()
    )
    stmt = (
        select(ranked.c.note_id, ranked.c.payload)
        .where(ranked.c.rank <= PREVIEW_NODE_LIMIT)
        .order_by(ranked.c.note_id, ranked.c.rank)
    )
    parts: dict[uuid.UUID, list[str]] = defaultdict(list)
    for note_id, payload in session.execute(stmt).tuples():
        if payload:
            parts[note_id].append(markdown_to_plain_text(payload))
    previews: dict[uuid.UUID, str] = {}
    for note_id, texts in parts.items():
        text = " ".join(t for t in texts if t)
        if text:
            previews[note_id] = _truncate(text, max_chars)
    return previews
