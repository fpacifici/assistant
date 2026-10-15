"""Tests for semantic search over note chunks and its permission filter."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding
from sqlalchemy.orm import Session

from assistant.models.schema import RoleName, User
from assistant.notes.entitlements import grant_entitlement
from assistant.notes.permissions import ViewableScope, viewable_scope
from assistant.notes.service import add_markdown_node, create_note, create_notebook
from assistant.vectors.indexer import VectorIndexer
from assistant.vectors.search import NoteSearcher, async_database_url, scope_filter
from assistant.vectors.store import EMBEDDING_DIMENSIONS

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy import Engine

    from assistant.models.schema import Note


def _user(session: Session, email: str) -> User:
    user = User(email=email, firstname="A", lastname="B")
    session.add(user)
    session.flush()
    return user


# --- Filter ---


def test_scope_filter_combines_notebooks_and_notes() -> None:
    notebook, note = uuid.uuid4(), uuid.uuid4()

    where = scope_filter(ViewableScope(frozenset({notebook}), frozenset({note})))

    assert where == {
        "$or": [
            {"notebook_id": {"$in": [str(notebook)]}},
            {"note_id": {"$in": [str(note)]}},
        ],
    }


def test_scope_filter_with_only_notebooks() -> None:
    notebook = uuid.uuid4()

    where = scope_filter(ViewableScope(frozenset({notebook}), frozenset()))

    assert where == {"notebook_id": {"$in": [str(notebook)]}}


def test_scope_filter_with_nothing_viewable() -> None:
    assert scope_filter(ViewableScope(frozenset(), frozenset())) is None


def test_async_url_uses_psycopg3(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db:5432/app")

    assert async_database_url() == "postgresql+psycopg://u:p@db:5432/app"


# --- Viewable scope ---


def test_viewable_scope_of_an_owner_and_a_note_viewer(db_session: Session) -> None:
    alice = _user(db_session, "alice@test.com")
    bob = _user(db_session, "bob@test.com")
    notebook = create_notebook(db_session, "Alice", alice)
    note = create_note(db_session, notebook_id=notebook.id, owner=alice, title="T")
    grant_entitlement(
        db_session,
        alice,
        note_id=note.id,
        grantee_email=bob.email,
        role_name=RoleName.NOTE_VIEWER,
    )

    assert viewable_scope(db_session, alice).notebook_ids == {notebook.id}
    bob_scope = viewable_scope(db_session, bob)
    assert bob_scope.notebook_ids == frozenset()
    assert bob_scope.note_ids == {note.id}


def test_viewable_scope_of_a_notebook_viewer(db_session: Session) -> None:
    alice = _user(db_session, "alice@test.com")
    bob = _user(db_session, "bob@test.com")
    notebook = create_notebook(db_session, "Alice", alice)
    grant_entitlement(
        db_session,
        alice,
        notebook_id=notebook.id,
        grantee_email=bob.email,
        role_name=RoleName.NOTEBOOK_VIEWER,
    )

    assert viewable_scope(db_session, bob).notebook_ids == {notebook.id}


def test_viewable_scope_of_a_stranger_is_empty(db_session: Session) -> None:
    _user(db_session, "alice@test.com")
    carol = _user(db_session, "carol@test.com")

    assert viewable_scope(db_session, carol).is_empty


# --- Searching (Postgres, committed data: the store has its own connections) ---


class _Corpus:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.alice = _user(session, f"alice-{uuid.uuid4()}@test.com")
        self.bob = _user(session, f"bob-{uuid.uuid4()}@test.com")
        self.carol = _user(session, f"carol-{uuid.uuid4()}@test.com")
        self.rome = self._note(self.alice, "Rome", "We saw the Colosseum.")
        self.paris = self._note(self.alice, "Paris", "We climbed the Eiffel tower.")
        self.berlin = self._note(self.bob, "Berlin", "We walked along the wall.")
        grant_entitlement(
            session,
            self.alice,
            note_id=self.paris.id,
            grantee_email=self.bob.email,
            role_name=RoleName.NOTE_VIEWER,
        )
        indexer = VectorIndexer(
            DeterministicFakeEmbedding(size=EMBEDDING_DIMENSIONS), "f"
        )
        for note in (self.rome, self.paris, self.berlin):
            indexer.index_note(session, note.id)
        session.commit()

    def _note(self, owner: User, title: str, text: str) -> Note:
        notebook = create_notebook(self.session, f"{title} {uuid.uuid4().hex[:6]}", owner)
        note = create_note(
            self.session, notebook_id=notebook.id, owner=owner, title=title
        )
        add_markdown_node(self.session, note.id, owner, text, "paragraph")
        return note

    def chunk_text(self, note: Note) -> str:
        header = f"Title: {note.title}\nNotebook: {note.notebook.name}"
        return f"{header}\n\n{note.nodes[0].payload}"

    def delete(self) -> None:
        for user in (self.alice, self.bob, self.carol):
            self.session.delete(user)
        self.session.commit()


@pytest.fixture
def corpus(_pg_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[_Corpus]:
    monkeypatch.setenv(
        "DATABASE_URL", _pg_engine.url.render_as_string(hide_password=False)
    )
    with Session(_pg_engine) as session:
        corpus = _Corpus(session)
        try:
            yield corpus
        finally:
            corpus.delete()


@pytest.fixture
def searcher() -> NoteSearcher:
    return NoteSearcher(DeterministicFakeEmbedding(size=EMBEDDING_DIMENSIONS))


@pytest.mark.postgres
def test_search_returns_the_closest_chunk_first(
    corpus: _Corpus,
    searcher: NoteSearcher,
) -> None:
    hits = searcher.search(corpus.session, corpus.alice, corpus.chunk_text(corpus.rome))

    assert hits[0].note_id == corpus.rome.id
    assert hits[0].title == "Rome"
    assert hits[0].notebook_id == corpus.rome.notebook_id
    assert hits[0].notebook_name == corpus.rome.notebook.name
    assert hits[0].content == corpus.chunk_text(corpus.rome)
    assert hits[0].score == pytest.approx(0.0, abs=1e-6)


@pytest.mark.postgres
def test_search_only_returns_viewable_notes(
    corpus: _Corpus,
    searcher: NoteSearcher,
) -> None:
    hits = searcher.search(corpus.session, corpus.bob, "where did we go?")

    assert {hit.note_id for hit in hits} == {corpus.berlin.id, corpus.paris.id}


@pytest.mark.postgres
def test_search_for_a_user_who_sees_nothing(
    corpus: _Corpus,
    searcher: NoteSearcher,
) -> None:
    assert searcher.search(corpus.session, corpus.carol, "anything") == []
