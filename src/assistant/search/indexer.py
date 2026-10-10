"""Keeps a note's search index entries in sync with its content.

The index is stored apart from the notes, in `NoteSearchIndex` (one row per
note) and `NodeSearchIndex` (one row per block); notes and nodes carry no
search data. `index_note` is called by the notes service on every note write
(from `_touch_note`, plus note creation), inside the same transaction, so the
index never lags behind the data. On Postgres, generated `search_vector`
columns are derived from the text written here.

This module must not import `assistant.notes.service` (which imports it).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from assistant.models.schema import Node, NodeSearchIndex, NodeType, Note, NoteSearchIndex
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
    """Rebuild the search index entries of one note and its blocks.

    Only rows whose text changed are written. Entries for blocks that no
    longer exist are removed here too; the database also drops them on
    delete (ON DELETE CASCADE), but not on SQLite without foreign keys.
    """
    session.flush()
    note = session.get(Note, note_id)
    if note is None:
        return

    existing = {
        entry.node_id: entry
        for entry in session.scalars(
            select(NodeSearchIndex).where(NodeSearchIndex.note_id == note_id),
        )
    }
    body: list[str] = []
    nodes = session.scalars(
        select(Node).where(Node.note_id == note_id).order_by(Node.position),
    )
    for node in nodes:
        text = _index_text(node_plain_text(node))
        entry = existing.pop(node.id, None)
        if entry is None:
            session.add(NodeSearchIndex(node_id=node.id, note_id=note_id, text=text))
        elif entry.text != text:
            entry.text = text
        if text:
            body.append(text)
    for stale in existing.values():
        session.delete(stale)

    title = _index_text(note.title)
    note_entry = session.get(NoteSearchIndex, note_id)
    if note_entry is None:
        note_entry = NoteSearchIndex(note_id=note_id)
        session.add(note_entry)
    note_entry.title = title
    note_entry.body = " ".join(body)
    note_entry.index_version = SEARCH_INDEX_VERSION
    session.flush()
