"""Tests for the reindex_search CLI, verified through search()."""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, call, patch

import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding
from sqlalchemy import delete, update

from assistant.cli.reindex_search import main
from assistant.models.schema import (
    NodeSearchIndex,
    Note,
    NoteSearchIndex,
    NoteVectorIndex,
    User,
)
from assistant.notes.service import add_markdown_node, create_note, create_notebook
from assistant.search.service import search
from assistant.vectors.indexer import VectorIndexer
from assistant.vectors.staleness import stale_note_ids
from assistant.vectors.store import EMBEDDING_DIMENSIONS

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


def _wipe_index(session: Session, note: Note, *, keep_version: bool = False) -> None:
    """Make a note unfindable.

    By default its index entries are removed, as for notes that predate the
    search index. With `keep_version` the entries stay, stamped with the
    current index version, but hold no text.
    """
    if keep_version:
        session.execute(
            update(NoteSearchIndex)
            .where(NoteSearchIndex.note_id == note.id)
            .values(title="", body=""),
        )
        session.execute(
            update(NodeSearchIndex)
            .where(NodeSearchIndex.note_id == note.id)
            .values(text=""),
        )
    else:
        session.execute(delete(NodeSearchIndex).where(NodeSearchIndex.note_id == note.id))
        session.execute(delete(NoteSearchIndex).where(NoteSearchIndex.note_id == note.id))
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
    _wipe_index(pg_session, current, keep_version=True)
    _wipe_index(pg_session, _make_note(pg_session, alice, "Paris"))

    assert _run(pg_session, "--stale-only", "--batch-size", "1") == 0

    assert not _found(pg_session, alice, "berlin")
    assert _found(pg_session, alice, "paris")


def test_stale_only_reindexes_notes_indexed_with_an_older_version(
    pg_session: Session,
) -> None:
    alice = _make_user(pg_session, "alice@test.com")
    note = _make_note(pg_session, alice, "Berlin")
    _wipe_index(pg_session, note, keep_version=True)
    pg_session.execute(
        update(NoteSearchIndex)
        .where(NoteSearchIndex.note_id == note.id)
        .values(index_version=NoteSearchIndex.index_version - 1),
    )

    assert _run(pg_session, "--stale-only") == 0

    assert _found(pg_session, alice, "berlin")


# --- Vectors ---


class _FlakyEmbeddings(DeterministicFakeEmbedding):
    """Fake embeddings failing for texts containing a marker word."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if any("unlucky" in text for text in texts):
            msg = "insufficient_quota"
            raise RuntimeError(msg)
        return super().embed_documents(texts)


def _run_vectors(session: Session, *args: str, sleep: MagicMock | None = None) -> int:
    indexer = VectorIndexer(_FlakyEmbeddings(size=EMBEDDING_DIMENSIONS), "fake")
    with (
        patch("assistant.cli.reindex_search.create_vector_indexer", return_value=indexer),
        patch("assistant.cli.reindex_search.time.sleep", sleep or MagicMock()),
    ):
        return _run(session, "--vectors", *args)


def _stale(session: Session) -> set[uuid.UUID]:
    return set(session.scalars(stale_note_ids()))


def test_vectors_embeds_every_note(pg_session: Session) -> None:
    alice = _make_user(pg_session, "alice@test.com")
    notes = [_make_note(pg_session, alice, text) for text in ("Berlin", "Paris")]

    assert _run_vectors(pg_session) == 0

    assert not _stale(pg_session) & {note.id for note in notes}


def test_vectors_stale_only_skips_fresh_notes(pg_session: Session) -> None:
    alice = _make_user(pg_session, "alice@test.com")
    fresh = _make_note(pg_session, alice, "Berlin")
    assert _run_vectors(pg_session) == 0
    fresh_entry = pg_session.get(NoteVectorIndex, fresh.id)
    assert fresh_entry is not None
    indexed_at = fresh_entry.indexed_at
    stale = _make_note(pg_session, alice, "Paris")

    assert _run_vectors(pg_session, "--stale-only") == 0

    pg_session.refresh(fresh_entry)
    assert fresh_entry.indexed_at == indexed_at
    assert stale.id not in _stale(pg_session)


def test_vectors_failures_are_skipped_and_reported(pg_session: Session) -> None:
    alice = _make_user(pg_session, "alice@test.com")
    broken = _make_note(pg_session, alice, "unlucky")
    fine = _make_note(pg_session, alice, "Paris")

    assert _run_vectors(pg_session) == 1

    assert broken.id in _stale(pg_session)
    assert fine.id not in _stale(pg_session)


def test_vectors_wait_between_two_notes(pg_session: Session) -> None:
    alice = _make_user(pg_session, "alice@test.com")
    for text in ("Berlin", "Paris", "Rome"):
        _make_note(pg_session, alice, text)
    sleep = MagicMock()

    assert _run_vectors(pg_session, "--user-id", str(alice.uid), sleep=sleep) == 0

    assert sleep.call_args_list == [call(0.25), call(0.25)]


def test_vectors_delay_is_configurable(pg_session: Session) -> None:
    alice = _make_user(pg_session, "alice@test.com")
    for text in ("Berlin", "Paris"):
        _make_note(pg_session, alice, text)
    sleep = MagicMock()

    assert (
        _run_vectors(
            pg_session, "--user-id", str(alice.uid), "--delay-ms", "1000", sleep=sleep
        )
        == 0
    )

    assert sleep.call_args_list == [call(1.0)]


def test_vectors_delay_zero_does_not_wait(pg_session: Session) -> None:
    alice = _make_user(pg_session, "alice@test.com")
    for text in ("Berlin", "Paris"):
        _make_note(pg_session, alice, text)
    sleep = MagicMock()

    assert (
        _run_vectors(
            pg_session, "--user-id", str(alice.uid), "--delay-ms", "0", sleep=sleep
        )
        == 0
    )

    sleep.assert_not_called()


def test_vectors_need_an_api_key(pg_session: Session) -> None:
    assert _run(pg_session, "--vectors") == 1
