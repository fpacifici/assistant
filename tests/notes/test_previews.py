"""Tests for note previews."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from assistant.models.schema import Note, User
from assistant.notes.previews import (
    PREVIEW_NODE_LIMIT,
    markdown_to_plain_text,
    note_previews,
)
from assistant.notes.service import (
    add_markdown_node,
    add_text_node,
    create_note,
    create_notebook,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _make_user(session: Session) -> User:
    user = User(email="u@test.com", firstname="A", lastname="B")
    session.add(user)
    session.flush()
    return user


def _make_note(session: Session, owner: User, title: str = "N") -> Note:
    notebook = create_notebook(session, "NB", owner)
    return create_note(session, notebook_id=notebook.id, owner=owner, title=title)


# --- markdown_to_plain_text ---


@pytest.mark.parametrize(
    ("markdown", "expected"),
    [
        ("# Heading", "Heading"),
        ("### Small heading", "Small heading"),
        ("- item", "item"),
        ("* item", "item"),
        ("1. first", "first"),
        ("- [x] done", "done"),
        ("> quoted", "quoted"),
        ("**bold** and *italic*", "bold and italic"),
        ("~~gone~~ `code`", "gone code"),
        ("see [the docs](https://example.com)", "see the docs"),
        ("![diagram](https://example.com/a.png)", "diagram"),
        ("line one\n\nline   two", "line one line two"),
        ("snake_case_name", "snake_case_name"),
        ("```python\nprint(1)\n```", "print(1)"),
    ],
)
def test_markdown_to_plain_text(markdown: str, expected: str) -> None:
    assert markdown_to_plain_text(markdown) == expected


# --- note_previews ---


def test_note_previews_empty_input(db_session: Session) -> None:
    assert note_previews(db_session, []) == {}


def test_note_previews_joins_first_blocks_in_order(db_session: Session) -> None:
    user = _make_user(db_session)
    note = _make_note(db_session, user)
    add_markdown_node(db_session, note.id, user, "# Hilbert curves", "heading")
    add_markdown_node(db_session, note.id, user, "A way to **sort** data", "paragraph")
    add_text_node(db_session, note.id, user, "plain text")

    previews = note_previews(db_session, [note.id])
    assert previews == {note.id: "Hilbert curves A way to sort data plain text"}


def test_note_previews_omits_notes_without_text(db_session: Session) -> None:
    user = _make_user(db_session)
    note = _make_note(db_session, user)
    add_text_node(db_session, note.id, user, "")

    assert note_previews(db_session, [note.id]) == {}


def test_note_previews_truncates_on_word_boundary(db_session: Session) -> None:
    user = _make_user(db_session)
    note = _make_note(db_session, user)
    add_text_node(db_session, note.id, user, "alpha beta gamma delta")

    previews = note_previews(db_session, [note.id], max_chars=13)
    assert previews[note.id] == "alpha beta…"


def test_note_previews_reads_only_the_first_nodes(db_session: Session) -> None:
    user = _make_user(db_session)
    note = _make_note(db_session, user)
    for i in range(PREVIEW_NODE_LIMIT + 3):
        add_text_node(db_session, note.id, user, f"n{i}")

    words = note_previews(db_session, [note.id])[note.id].split()
    assert words == [f"n{i}" for i in range(PREVIEW_NODE_LIMIT)]


def test_note_previews_batches_several_notes(db_session: Session) -> None:
    user = _make_user(db_session)
    notebook = create_notebook(db_session, "NB", user)
    first = create_note(db_session, notebook_id=notebook.id, owner=user, title="1")
    second = create_note(db_session, notebook_id=notebook.id, owner=user, title="2")
    add_text_node(db_session, first.id, user, "first body")
    add_text_node(db_session, second.id, user, "second body")

    previews = note_previews(db_session, [first.id, second.id])
    assert previews == {first.id: "first body", second.id: "second body"}
