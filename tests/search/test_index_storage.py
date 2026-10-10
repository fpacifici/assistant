"""The search index is stored apart from the notes (against Postgres).

Notes and nodes carry no search columns; the index lives in its own tables,
keyed by foreign keys, and goes away with the note or block it indexes.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import func, inspect, select

from assistant.models.schema import NodeSearchIndex, NoteSearchIndex, User
from assistant.notes.service import (
    add_markdown_node,
    create_note,
    create_notebook,
    delete_node,
    delete_note,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

pytestmark = pytest.mark.postgres


def _make_user(session: Session) -> User:
    user = User(email="owner@test.com", firstname="A", lastname="B")
    session.add(user)
    session.flush()
    return user


def _count(session: Session, model: type, note_id: uuid.UUID) -> int:
    return session.scalar(
        select(func.count()).select_from(model).where(model.note_id == note_id)
    )


def test_notes_and_nodes_have_no_search_columns(pg_session: Session) -> None:
    inspector = inspect(pg_session.connection())

    for table in ("notes", "nodes"):
        columns = {c["name"] for c in inspector.get_columns(table, schema="assistant")}
        assert not {c for c in columns if c.startswith("search")}, table


def test_deleting_a_note_deletes_its_index(pg_session: Session) -> None:
    owner = _make_user(pg_session)
    notebook = create_notebook(pg_session, "NB", owner)
    note = create_note(pg_session, notebook_id=notebook.id, owner=owner, title="Berlin")
    add_markdown_node(pg_session, note.id, owner, "Paris", "paragraph")
    assert _count(pg_session, NoteSearchIndex, note.id) == 1
    assert _count(pg_session, NodeSearchIndex, note.id) == 1

    delete_note(pg_session, note.id, owner)

    assert _count(pg_session, NoteSearchIndex, note.id) == 0
    assert _count(pg_session, NodeSearchIndex, note.id) == 0


def test_deleting_a_block_deletes_its_index_entry(pg_session: Session) -> None:
    owner = _make_user(pg_session)
    notebook = create_notebook(pg_session, "NB", owner)
    note = create_note(pg_session, notebook_id=notebook.id, owner=owner, title="Berlin")
    node = add_markdown_node(pg_session, note.id, owner, "Paris", "paragraph")
    add_markdown_node(pg_session, note.id, owner, "Rome", "paragraph")

    delete_node(pg_session, node.id, owner)

    assert pg_session.get(NodeSearchIndex, node.id) is None
    assert _count(pg_session, NodeSearchIndex, note.id) == 1
