"""Tests for the search service, against a real Postgres (`pg_session`).

Notes are created and edited only through the notes service, so these
tests also cover indexing end to end: whatever a user writes must be
findable right away.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from assistant.models.schema import Note, User
from assistant.notes.service import add_markdown_node, create_note, create_notebook
from assistant.search.service import search

pytestmark = pytest.mark.postgres


def _make_user(session: Session, email: str = "owner@test.com") -> User:
    user = User(email=email, firstname="A", lastname="B")
    session.add(user)
    session.flush()
    return user


def _make_note(
    session: Session,
    owner: User,
    title: str = "Untitled",
    blocks: tuple[str, ...] = (),
) -> Note:
    notebook = create_notebook(session, f"NB {uuid.uuid4()}", owner)
    note = create_note(session, notebook_id=notebook.id, owner=owner, title=title)
    for payload in blocks:
        add_markdown_node(session, note.id, owner, payload, "paragraph")
    return note


def _hit_ids(session: Session, user: User, query: str) -> list:
    return [hit.note.id for hit in search(session, user, query).hits]


# --- Keyword matching ---


def test_finds_note_by_word_in_a_block(pg_session: Session) -> None:
    owner = _make_user(pg_session)
    match = _make_note(pg_session, owner, blocks=("We fly to Berlin on Monday",))
    _make_note(pg_session, owner, blocks=("Grocery list",))

    assert _hit_ids(pg_session, owner, "berlin") == [match.id]
