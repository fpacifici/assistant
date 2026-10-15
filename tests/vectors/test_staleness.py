"""Tests for marking notes stale and announcing them after commit."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from assistant.models.schema import NoteVectorIndex, User
from assistant.notes.service import (
    add_markdown_node,
    create_note,
    create_notebook,
    update_note,
    update_notebook,
)
from assistant.vectors.indexer import VECTOR_INDEX_VERSION
from assistant.vectors.staleness import (
    mark_notes_stale,
    set_stale_listener,
    stale_note_ids,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.orm import Session

    from assistant.models.schema import Note


@pytest.fixture
def announced() -> Iterator[list[list[uuid.UUID]]]:
    """Note ids handed to the stale listener, one list per commit."""
    calls: list[list[uuid.UUID]] = []
    set_stale_listener(calls.append)
    yield calls
    set_stale_listener(None)


def _user(session: Session) -> User:
    user = User(email=f"{uuid.uuid4()}@test.com", firstname="A", lastname="B")
    session.add(user)
    session.flush()
    return user


def _note(session: Session, owner: User, notebook_name: str = "NB") -> Note:
    notebook = create_notebook(session, notebook_name, owner)
    return create_note(session, notebook_id=notebook.id, owner=owner, title="T")


def _indexed(session: Session, note_id: uuid.UUID, at: datetime) -> NoteVectorIndex:
    entry = NoteVectorIndex(
        note_id=note_id,
        content_hash="h",
        index_version=VECTOR_INDEX_VERSION,
        indexed_at=at,
    )
    session.add(entry)
    session.flush()
    return entry


def _stale(session: Session) -> set[uuid.UUID]:
    return set(session.scalars(stale_note_ids()))


# --- Announcing after commit ---


def test_new_note_is_announced_after_commit(
    db_session: Session,
    announced: list[list[uuid.UUID]],
) -> None:
    note = _note(db_session, _user(db_session))
    assert announced == []

    db_session.commit()

    assert announced == [[note.id]]


def test_edits_in_one_transaction_are_announced_once(
    db_session: Session,
    announced: list[list[uuid.UUID]],
) -> None:
    owner = _user(db_session)
    note = _note(db_session, owner)
    add_markdown_node(db_session, note.id, owner, "one", "paragraph")
    add_markdown_node(db_session, note.id, owner, "two", "paragraph")

    db_session.commit()

    assert announced == [[note.id]]


def test_rollback_forgets_marked_notes(
    db_session: Session,
    announced: list[list[uuid.UUID]],
) -> None:
    _note(db_session, _user(db_session))

    db_session.rollback()
    db_session.commit()

    assert announced == []


def test_without_listener_commit_works(db_session: Session) -> None:
    _note(db_session, _user(db_session))

    db_session.commit()


def test_failing_listener_does_not_break_the_commit(db_session: Session) -> None:
    def explode(_ids: list[uuid.UUID]) -> None:
        raise RuntimeError

    set_stale_listener(explode)
    try:
        _note(db_session, _user(db_session))
        db_session.commit()
    finally:
        set_stale_listener(None)


# --- What makes a note stale ---


def test_never_indexed_note_is_stale(db_session: Session) -> None:
    note = _note(db_session, _user(db_session))

    assert _stale(db_session) == {note.id}


def test_indexed_note_is_fresh(db_session: Session) -> None:
    note = _note(db_session, _user(db_session))
    _indexed(db_session, note.id, datetime.now(UTC))

    assert _stale(db_session) == set()


def test_editing_an_indexed_note_makes_it_stale(db_session: Session) -> None:
    owner = _user(db_session)
    note = _note(db_session, owner)
    _indexed(db_session, note.id, datetime.now(UTC) - timedelta(seconds=1))

    update_note(db_session, note.id, owner, title="New title")

    assert _stale(db_session) == {note.id}


def test_edit_before_the_indexer_read_the_note_stays_fresh(db_session: Session) -> None:
    note = _note(db_session, _user(db_session))
    entry = _indexed(db_session, note.id, datetime.now(UTC))
    entry.stale_since = entry.indexed_at - timedelta(seconds=1)  # type: ignore[operator]
    db_session.flush()

    assert _stale(db_session) == set()


def test_older_index_version_is_stale(db_session: Session) -> None:
    note = _note(db_session, _user(db_session))
    entry = _indexed(db_session, note.id, datetime.now(UTC))
    entry.index_version = VECTOR_INDEX_VERSION - 1
    db_session.flush()

    assert _stale(db_session) == {note.id}


def test_renaming_a_notebook_marks_all_its_notes(
    db_session: Session,
    announced: list[list[uuid.UUID]],
) -> None:
    owner = _user(db_session)
    notebook = create_notebook(db_session, "Old", owner)
    notes = [
        create_note(db_session, notebook_id=notebook.id, owner=owner, title=t)
        for t in ("a", "b")
    ]
    for note in notes:
        _indexed(db_session, note.id, datetime.now(UTC) - timedelta(seconds=1))
    db_session.commit()
    announced.clear()

    update_notebook(db_session, notebook.id, owner, name="New")
    db_session.commit()

    assert _stale(db_session) == {note.id for note in notes}
    assert announced == [sorted(note.id for note in notes)]


def test_keeping_the_notebook_name_marks_nothing(
    db_session: Session,
    announced: list[list[uuid.UUID]],
) -> None:
    owner = _user(db_session)
    note = _note(db_session, owner, notebook_name="Same")
    _indexed(db_session, note.id, datetime.now(UTC) - timedelta(seconds=1))
    db_session.commit()
    announced.clear()

    update_notebook(db_session, note.notebook_id, owner, name="Same")
    db_session.commit()

    assert _stale(db_session) == set()
    assert announced == []


def test_marking_nothing_is_a_no_op(
    db_session: Session,
    announced: list[list[uuid.UUID]],
) -> None:
    mark_notes_stale(db_session, [])
    db_session.commit()

    assert announced == []
