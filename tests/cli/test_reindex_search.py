"""Tests for the reindex_search CLI, verified through search()."""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from sqlalchemy import update

from assistant.cli.reindex_search import main
from assistant.models.schema import Node, Note, User
from assistant.notes.service import add_markdown_node, create_note, create_notebook
from assistant.search.service import search

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.orm import Session

pytestmark = pytest.mark.postgres


def _make_user(session: Session, email: str) -> User:
    user = User(email=email, firstname="A", lastname="B")
    session.add(user)
    session.flush()
    return user


def _make_note(session: Session, owner: User, text: str) -> Note:
    notebook = create_notebook(session, f"NB {uuid.uuid4()}", owner)
    note = create_note(session, notebook_id=notebook.id, owner=owner, title="Note")
    add_markdown_node(session, note.id, owner, text, "paragraph")
    return note


def _wipe_index(session: Session, note: Note, *, version: int = 0) -> None:
    """Make a note look like it predates the search index."""
    session.execute(
        update(Note)
        .where(Note.id == note.id)
        .values(search_title="", search_body="", search_index_version=version),
    )
    session.execute(update(Node).where(Node.note_id == note.id).values(search_text=""))
    session.expire_all()


def _run(session: Session, *args: str) -> int:
    @contextmanager
    def factory() -> Iterator[Session]:
        yield session

    with patch("assistant.cli.reindex_search.get_session_factory", return_value=factory):
        return main(list(args))


def _found(session: Session, user: User, word: str) -> bool:
    return bool(search(session, user, f"{word} ").hits)


# --- Reindex ---


def test_reindexes_every_note(pg_session: Session) -> None:
    alice = _make_user(pg_session, "alice@test.com")
    bob = _make_user(pg_session, "bob@test.com")
    _wipe_index(pg_session, _make_note(pg_session, alice, "Berlin"))
    _wipe_index(pg_session, _make_note(pg_session, bob, "Paris"))

    assert _run(pg_session) == 0

    assert _found(pg_session, alice, "berlin")
    assert _found(pg_session, bob, "paris")


def test_reindexes_only_the_given_users_notes(pg_session: Session) -> None:
    alice = _make_user(pg_session, "alice@test.com")
    bob = _make_user(pg_session, "bob@test.com")
    _wipe_index(pg_session, _make_note(pg_session, alice, "Berlin"))
    _wipe_index(pg_session, _make_note(pg_session, bob, "Paris"))

    assert _run(pg_session, "--user-id", str(alice.uid)) == 0

    assert _found(pg_session, alice, "berlin")
    assert not _found(pg_session, bob, "paris")


def test_stale_only_skips_notes_indexed_with_the_current_version(
    pg_session: Session,
) -> None:
    alice = _make_user(pg_session, "alice@test.com")
    current = _make_note(pg_session, alice, "Berlin")
    _wipe_index(pg_session, current, version=current.search_index_version)
    _wipe_index(pg_session, _make_note(pg_session, alice, "Paris"))

    assert _run(pg_session, "--stale-only", "--batch-size", "1") == 0

    assert not _found(pg_session, alice, "berlin")
    assert _found(pg_session, alice, "paris")
