"""Keeps a note's search index columns in sync with its content.

`index_note` is called by the notes service on every note write (from
`_touch_note`, plus note creation), inside the same transaction, so the
index never lags behind the data. On Postgres, generated `search_vector`
columns are derived from the text written here.

This module must not import `assistant.notes.service` (which imports it).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from assistant.models.schema import Node, NodeType, Note
from assistant.search.analysis import SEARCH_INDEX_VERSION, analyze, markdown_to_plain

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session


def node_plain_text(node: Node) -> str:
    """The readable text of a node, as shown in snippets.

    Markdown and attachment nodes (whose payload is a markdown link to the
    file) have their markdown stripped; legacy text nodes are plain already.
    """
    payload = node.payload or ""
    if node.node_type == NodeType.TEXT:
        return payload
    return markdown_to_plain(payload)


def _index_text(text: str) -> str:
    return " ".join(analyze(text))


def index_note(session: Session, note_id: uuid.UUID) -> None:
    """Recompute the search index columns of one note and its nodes."""
    session.flush()
    note = session.get(Note, note_id)
    if note is None:
        return
    nodes = session.scalars(
        select(Node).where(Node.note_id == note_id).order_by(Node.position),
    )
    body: list[str] = []
    for node in nodes:
        text = _index_text(node_plain_text(node))
        if node.search_text != text:
            node.search_text = text
        if text:
            body.append(text)
    note.search_title = _index_text(note.title)
    note.search_body = " ".join(body)
    note.search_index_version = SEARCH_INDEX_VERSION
    session.flush()
