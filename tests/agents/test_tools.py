"""Tests for the Ask AI agent's tools and their permission checks."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

from assistant.agents.tools import MAX_NOTE_CHARS, build_tools, unique_sources
from assistant.models.schema import RoleName, User
from assistant.notes.entitlements import grant_entitlement
from assistant.notes.service import add_markdown_node, create_note, create_notebook
from tests.agents.fakes import FakeSearcher, hit

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager

    from langchain_core.messages import ToolMessage
    from langchain_core.tools import BaseTool
    from sqlalchemy.orm import Session

    from assistant.models.schema import Note

    SessionFactory = Callable[[], AbstractContextManager[Session]]


def _user(session: Session, email: str) -> User:
    user = User(email=email, firstname="A", lastname="B")
    session.add(user)
    session.flush()
    return user


def _note(session: Session, owner: User, title: str, *paragraphs: str) -> Note:
    notebook = create_notebook(session, f"Travel {uuid.uuid4().hex[:6]}", owner)
    note = create_note(session, notebook_id=notebook.id, owner=owner, title=title)
    for text in paragraphs:
        add_markdown_node(session, note.id, owner, text, "paragraph")
    return note


def _tools(
    factory: SessionFactory,
    user: User,
    searcher: FakeSearcher | None = None,
) -> dict[str, BaseTool]:
    tools = build_tools(factory, user.uid, searcher or FakeSearcher())  # type: ignore[arg-type]
    return {t.name: t for t in tools}


def _call(tool: BaseTool, **args: object) -> ToolMessage:
    return tool.invoke(
        {"name": tool.name, "args": args, "id": "call-1", "type": "tool_call"}
    )


# --- search_notes ---


def test_search_notes_searches_as_the_user(
    db_session: Session,
    db_session_factory: SessionFactory,
) -> None:
    alice = _user(db_session, "alice@test.com")
    note_id = uuid.uuid4()
    searcher = FakeSearcher(
        [hit(note_id, "Rome", "Colosseum"), hit(note_id, "Rome", "Pasta")]
    )

    result = _call(
        _tools(db_session_factory, alice, searcher)["search_notes"], query="trip"
    )

    assert searcher.queries == [(alice.uid, "trip")]
    assert f"note_id: {note_id}" in result.content
    assert "Colosseum" in result.content
    assert "Pasta" in result.content
    assert [s["note_id"] for s in result.artifact] == [str(note_id)]


def test_search_notes_without_hits(
    db_session: Session,
    db_session_factory: SessionFactory,
) -> None:
    alice = _user(db_session, "alice@test.com")

    result = _call(_tools(db_session_factory, alice)["search_notes"], query="trip")

    assert result.content == "No matching notes."
    assert result.artifact == []


# --- get_note ---


def test_get_note_returns_the_whole_note(
    db_session: Session,
    db_session_factory: SessionFactory,
) -> None:
    alice = _user(db_session, "alice@test.com")
    note = _note(db_session, alice, "Rome", "Day one.", "Day two.")

    result = _call(_tools(db_session_factory, alice)["get_note"], note_id=str(note.id))

    assert result.content.startswith("Title: Rome\nNotebook: Travel")
    assert result.content.endswith("Day one.\n\nDay two.")
    assert result.artifact == [
        {
            "note_id": str(note.id),
            "notebook_id": str(note.notebook_id),
            "title": "Rome",
            "notebook_name": note.notebook.name,
        },
    ]


def test_get_note_hides_notes_the_user_cannot_view(
    db_session: Session,
    db_session_factory: SessionFactory,
) -> None:
    alice = _user(db_session, "alice@test.com")
    bob = _user(db_session, "bob@test.com")
    note = _note(db_session, alice, "Secret", "Hidden text.")

    result = _call(_tools(db_session_factory, bob)["get_note"], note_id=str(note.id))

    assert result.content == "Note not found."
    assert result.artifact == []


def test_get_note_reads_notes_shared_with_the_user(
    db_session: Session,
    db_session_factory: SessionFactory,
) -> None:
    alice = _user(db_session, "alice@test.com")
    bob = _user(db_session, "bob@test.com")
    note = _note(db_session, alice, "Shared", "Visible text.")
    grant_entitlement(
        db_session,
        alice,
        note_id=note.id,
        grantee_email=bob.email,
        role_name=RoleName.NOTE_VIEWER,
    )

    result = _call(_tools(db_session_factory, bob)["get_note"], note_id=str(note.id))

    assert "Visible text." in result.content


def test_get_note_rejects_invalid_ids(
    db_session: Session,
    db_session_factory: SessionFactory,
) -> None:
    alice = _user(db_session, "alice@test.com")

    result = _call(_tools(db_session_factory, alice)["get_note"], note_id="not-an-id")

    assert result.content == "Invalid note_id: 'not-an-id'"


def test_get_note_truncates_long_notes(
    db_session: Session,
    db_session_factory: SessionFactory,
) -> None:
    alice = _user(db_session, "alice@test.com")
    note = _note(db_session, alice, "Long", "x" * (MAX_NOTE_CHARS + 10))

    result = _call(_tools(db_session_factory, alice)["get_note"], note_id=str(note.id))

    assert result.content.endswith("[note truncated]")


# --- keyword_search (Postgres full text search) ---


@pytest.mark.postgres
def test_keyword_search_finds_only_viewable_notes(
    pg_session: Session,
    pg_session_factory: SessionFactory,
) -> None:
    alice = _user(pg_session, f"alice-{uuid.uuid4()}@test.com")
    bob = _user(pg_session, f"bob-{uuid.uuid4()}@test.com")
    mine = _note(pg_session, bob, "Mine", "The zebra crossing.")
    _note(pg_session, alice, "Alice's", "Another zebra.")

    result = _call(_tools(pg_session_factory, bob)["keyword_search"], query="zebra")

    assert f"note_id: {mine.id}" in result.content
    assert "Title: Mine" in result.content
    assert "zebra" in result.content
    assert [s["note_id"] for s in result.artifact] == [str(mine.id)]


@pytest.mark.postgres
def test_keyword_search_without_matches(
    pg_session: Session,
    pg_session_factory: SessionFactory,
) -> None:
    bob = _user(pg_session, f"bob-{uuid.uuid4()}@test.com")

    result = _call(_tools(pg_session_factory, bob)["keyword_search"], query="zebra")

    assert result.content == "No matching notes."


@pytest.mark.postgres
def test_keyword_search_with_no_words(
    pg_session: Session,
    pg_session_factory: SessionFactory,
) -> None:
    bob = _user(pg_session, f"bob-{uuid.uuid4()}@test.com")

    result = _call(_tools(pg_session_factory, bob)["keyword_search"], query="!!!")

    assert result.content == "The query has no words to search for."


# --- Helpers ---


def test_unique_sources_keeps_first_occurrence() -> None:
    a = {"note_id": "1", "notebook_id": "n", "title": "A", "notebook_name": "N"}
    b = {"note_id": "2", "notebook_id": "n", "title": "B", "notebook_name": "N"}

    assert unique_sources([a, b, a]) == [a, b]  # type: ignore[list-item]
