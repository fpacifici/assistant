"""Tests for the Ask AI agent: streamed events, history, errors."""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import httpx
import openai
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from assistant.agents.rag import (
    AskAgent,
    ChatMessage,
    DoneEvent,
    ErrorEvent,
    SourcesEvent,
    TokenEvent,
    ToolEvent,
    create_ask_agent,
    error_message,
    event_payload,
    history_from_messages,
)
from assistant.models.schema import User
from assistant.notes.service import create_note, create_notebook
from tests.agents.fakes import (
    FakeSearcher,
    MemoryCheckpointer,
    ScriptedChatModel,
    hit,
    tool_call,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager

    from sqlalchemy.orm import Session

    from assistant.agents.rag import AskEvent
    from assistant.models.schema import Note

SessionFactory = "Callable[[], AbstractContextManager[Session]]"


@pytest.fixture
def owner(db_session: Session) -> User:
    user = User(email="owner@test.com", firstname="A", lastname="B")
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def note(db_session: Session, owner: User) -> Note:
    notebook = create_notebook(db_session, "Travel", owner)
    return create_note(db_session, notebook_id=notebook.id, owner=owner, title="Rome")


def _agent(
    session_factory: Callable[[], AbstractContextManager[Session]],
    model: ScriptedChatModel,
    searcher: FakeSearcher | None = None,
    checkpointer: MemoryCheckpointer | None = None,
) -> AskAgent:
    return AskAgent(
        session_factory,  # type: ignore[arg-type]
        searcher or FakeSearcher(),  # type: ignore[arg-type]
        model,
        checkpointer=checkpointer or MemoryCheckpointer(),
    )


def _answer(events: list[AskEvent]) -> str:
    return "".join(e.text for e in events if isinstance(e, TokenEvent))


# --- Streaming ---


def test_streams_tool_calls_answer_and_sources(
    db_session_factory: Callable[[], AbstractContextManager[Session]],
    owner: User,
    note: Note,
) -> None:
    searcher = FakeSearcher([hit(note.id, "Rome", "We saw the Colosseum.")])
    model = ScriptedChatModel(
        script=[
            tool_call("search_notes", query="trip"),
            AIMessage(content="You saw the Colosseum."),
        ],
    )
    agent = _agent(db_session_factory, model, searcher)

    events = list(agent.stream(uuid.uuid4(), owner.uid, "What did I see?"))

    assert events[0] == ToolEvent(
        name="search_notes", status="start", input={"query": "trip"}
    )
    assert events[1] == ToolEvent(name="search_notes", status="end")
    assert _answer(events) == "You saw the Colosseum."
    sources = [e for e in events if isinstance(e, SourcesEvent)]
    assert sources == [
        SourcesEvent(
            sources=[
                {
                    "note_id": str(note.id),
                    "notebook_id": str(searcher.hits[0].notebook_id),
                    "title": "Rome",
                    "notebook_name": "Travel",
                },
            ],
        ),
    ]
    assert events[-1] == DoneEvent()
    assert searcher.queries == [(owner.uid, "trip")]


def test_answer_without_tools_has_no_sources(
    db_session_factory: Callable[[], AbstractContextManager[Session]],
    owner: User,
) -> None:
    model = ScriptedChatModel(script=[AIMessage(content="Hello!")])

    events = list(_agent(db_session_factory, model).stream(uuid.uuid4(), owner.uid, "Hi"))

    assert events == [TokenEvent(text="Hello!"), SourcesEvent(sources=[]), DoneEvent()]


def test_model_failure_is_an_error_event(
    db_session_factory: Callable[[], AbstractContextManager[Session]],
    owner: User,
) -> None:
    model = ScriptedChatModel(script=[], error=RuntimeError("boom"))

    events = list(_agent(db_session_factory, model).stream(uuid.uuid4(), owner.uid, "Hi"))

    assert events == [
        ErrorEvent(message="Something went wrong while answering. Try again."),
        DoneEvent(),
    ]


def test_runs_are_tagged_with_user_and_thread(
    db_session_factory: Callable[[], AbstractContextManager[Session]],
    owner: User,
) -> None:
    thread_id = uuid.uuid4()
    compiled = MagicMock()
    compiled.stream.return_value = iter([])
    agent = _agent(db_session_factory, ScriptedChatModel(script=[]))

    with patch("assistant.agents.rag.create_agent", return_value=compiled):
        list(agent.stream(thread_id, owner.uid, "Hi"))

    config = compiled.stream.call_args.args[1]
    assert config["configurable"] == {"thread_id": str(thread_id)}
    assert config["metadata"] == {"user_id": str(owner.uid), "thread_id": str(thread_id)}


# --- History ---


def test_history_keeps_questions_and_answers_with_sources(
    db_session_factory: Callable[[], AbstractContextManager[Session]],
    owner: User,
    note: Note,
) -> None:
    model = ScriptedChatModel(
        script=[
            tool_call("get_note", note_id=str(note.id)),
            AIMessage(content="It is about Rome."),
            AIMessage(content="Nothing else."),
        ],
    )
    agent = _agent(db_session_factory, model)
    thread_id = uuid.uuid4()
    list(agent.stream(thread_id, owner.uid, "What is my note about?"))
    list(agent.stream(thread_id, owner.uid, "Anything else?"))

    history = agent.history(thread_id)

    source = {
        "note_id": str(note.id),
        "notebook_id": str(note.notebook_id),
        "title": "Rome",
        "notebook_name": "Travel",
    }
    assert history == [
        ChatMessage(role="user", content="What is my note about?"),
        ChatMessage(role="assistant", content="It is about Rome.", sources=[source]),
        ChatMessage(role="user", content="Anything else?"),
        ChatMessage(role="assistant", content="Nothing else.", sources=[]),
    ]


def test_new_thread_has_no_history(
    db_session_factory: Callable[[], AbstractContextManager[Session]],
) -> None:
    agent = _agent(db_session_factory, ScriptedChatModel(script=[]))

    assert agent.history(uuid.uuid4()) == []


def test_delete_history(
    db_session_factory: Callable[[], AbstractContextManager[Session]],
    owner: User,
) -> None:
    agent = _agent(
        db_session_factory, ScriptedChatModel(script=[AIMessage(content="Hi")])
    )
    thread_id = uuid.uuid4()
    list(agent.stream(thread_id, owner.uid, "Hello"))

    agent.delete_history(thread_id)

    assert agent.history(thread_id) == []


def test_history_from_messages_merges_sources_of_one_answer() -> None:
    first = {"note_id": "1", "notebook_id": "n", "title": "A", "notebook_name": "N"}
    second = {"note_id": "2", "notebook_id": "n", "title": "B", "notebook_name": "N"}
    messages = [
        HumanMessage(content="q"),
        tool_call("search_notes", query="q"),
        ToolMessage(content="x", tool_call_id="1", artifact=[first, second]),
        ToolMessage(content="y", tool_call_id="2", artifact=[first]),
        AIMessage(content=[{"type": "text", "text": "answer"}]),
    ]

    assert history_from_messages(messages) == [
        ChatMessage(role="user", content="q"),
        ChatMessage(role="assistant", content="answer", sources=[first, second]),
    ]


# --- Errors and payloads ---


def _response(status: int) -> httpx.Response:
    return httpx.Response(status, request=httpx.Request("POST", "https://api.openai.com"))


def test_error_message_for_missing_credits() -> None:
    exc = openai.RateLimitError(
        "You exceeded your current quota (insufficient_quota)",
        response=_response(429),
        body=None,
    )

    assert (
        error_message(exc) == "The AI service has no credits left. Ask the administrator."
    )


def test_error_message_for_rate_limits() -> None:
    exc = openai.RateLimitError("Slow down", response=_response(429), body=None)

    assert error_message(exc) == "The AI service is busy. Try again in a minute."


def test_error_message_for_outages() -> None:
    exc = openai.InternalServerError("down", response=_response(500), body=None)

    assert (
        error_message(exc) == "The AI service is unavailable right now. Try again later."
    )


def test_event_payloads() -> None:
    assert json.loads(event_payload(TokenEvent(text="Hi"))) == {"text": "Hi"}
    assert json.loads(event_payload(ToolEvent(name="t", status="end"))) == {
        "name": "t",
        "status": "end",
        "input": {},
    }
    assert json.loads(event_payload(SourcesEvent(sources=[]))) == {"sources": []}
    assert json.loads(event_payload(ErrorEvent(message="m"))) == {"message": "m"}
    assert json.loads(event_payload(DoneEvent())) == {}


# --- Configuration ---


def test_no_agent_without_api_key(
    db_session_factory: Callable[[], AbstractContextManager[Session]],
) -> None:
    assert create_ask_agent(db_session_factory) is None  # type: ignore[arg-type]


def test_agent_built_when_api_key_is_set(
    db_session_factory: Callable[[], AbstractContextManager[Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    with patch("langchain_openai.OpenAIEmbeddings"):
        agent = create_ask_agent(db_session_factory)  # type: ignore[arg-type]

    assert isinstance(agent, AskAgent)
