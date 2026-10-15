"""Tests for Ask AI threads."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from assistant.chat.exceptions import ChatThreadNotFoundError
from assistant.chat.service import (
    TITLE_MAX_LENGTH,
    create_thread,
    delete_thread,
    get_thread,
    list_threads,
    record_question,
    title_from_question,
)
from assistant.models.schema import ChatThread, User

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _user(session: Session, email: str = "alice@test.com") -> User:
    user = User(email=email, firstname="A", lastname="B")
    session.add(user)
    session.flush()
    return user


# --- Create and get ---


def test_new_thread_is_untitled(db_session: Session) -> None:
    alice = _user(db_session)

    thread = create_thread(db_session, alice)

    assert thread.user_id == alice.uid
    assert thread.title == ""
    assert get_thread(db_session, alice, thread.id) is thread


def test_other_users_threads_are_not_found(db_session: Session) -> None:
    alice = _user(db_session)
    bob = _user(db_session, "bob@test.com")
    thread = create_thread(db_session, alice)

    with pytest.raises(ChatThreadNotFoundError):
        get_thread(db_session, bob, thread.id)


def test_missing_thread_is_not_found(db_session: Session) -> None:
    with pytest.raises(ChatThreadNotFoundError):
        get_thread(db_session, _user(db_session), uuid.uuid4())


# --- List ---


def test_threads_are_listed_most_recent_first(db_session: Session) -> None:
    alice = _user(db_session)
    bob = _user(db_session, "bob@test.com")
    older = create_thread(db_session, alice)
    newer = create_thread(db_session, alice)
    older.updated_at = datetime.now(UTC) - timedelta(days=1)
    create_thread(db_session, bob)
    db_session.flush()

    assert list_threads(db_session, alice) == [newer, older]
    assert list_threads(db_session, alice, offset=1, limit=1) == [older]


# --- Questions ---


def test_first_question_becomes_the_title(db_session: Session) -> None:
    alice = _user(db_session)
    thread = create_thread(db_session, alice)
    before = thread.updated_at

    record_question(db_session, alice, thread.id, "Where  did I\ngo in May?")
    record_question(db_session, alice, thread.id, "And in June?")

    assert thread.title == "Where did I go in May?"
    assert thread.updated_at >= before


def test_long_questions_are_shortened_for_the_title() -> None:
    title = title_from_question("word " * 100)

    assert len(title) == TITLE_MAX_LENGTH
    assert title.endswith("…")


def test_questions_only_in_own_threads(db_session: Session) -> None:
    alice = _user(db_session)
    bob = _user(db_session, "bob@test.com")
    thread = create_thread(db_session, alice)

    with pytest.raises(ChatThreadNotFoundError):
        record_question(db_session, bob, thread.id, "Hi")


# --- Delete ---


def test_delete_thread(db_session: Session) -> None:
    alice = _user(db_session)
    thread = create_thread(db_session, alice)

    delete_thread(db_session, alice, thread.id)

    assert db_session.get(ChatThread, thread.id) is None


def test_cannot_delete_other_users_threads(db_session: Session) -> None:
    alice = _user(db_session)
    bob = _user(db_session, "bob@test.com")
    thread = create_thread(db_session, alice)

    with pytest.raises(ChatThreadNotFoundError):
        delete_thread(db_session, bob, thread.id)


def test_deleting_the_user_deletes_their_threads(db_session: Session) -> None:
    alice = _user(db_session)
    thread_id = create_thread(db_session, alice).id

    db_session.delete(alice)
    db_session.flush()

    assert db_session.get(ChatThread, thread_id) is None
