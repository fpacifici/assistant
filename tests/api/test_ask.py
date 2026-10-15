"""Tests for the Ask AI endpoints."""

from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from assistant.agents.rag import AskAgent
from assistant.api.app import create_app
from assistant.api.dependencies import get_session
from assistant.chat.service import create_thread
from assistant.notes.service import create_note, create_notebook
from tests.agents.fakes import (
    FakeSearcher,
    MemoryCheckpointer,
    ScriptedChatModel,
    hit,
    tool_call,
)

if TYPE_CHECKING:
    from collections.abc import Generator, Iterator

    from sqlalchemy.orm import Session

    from assistant.models.schema import User


@pytest.fixture
def model() -> ScriptedChatModel:
    return ScriptedChatModel(script=[])


@pytest.fixture
def searcher() -> FakeSearcher:
    return FakeSearcher()


@pytest.fixture
def ask_client(
    db_session: Session,
    model: ScriptedChatModel,
    searcher: FakeSearcher,
) -> Iterator[TestClient]:
    """A client whose app has an agent on a scripted model."""

    @contextmanager
    def session_factory() -> Iterator[Session]:
        yield db_session

    def override_get_session() -> Generator[Session]:
        yield db_session

    agent = AskAgent(
        session_factory,  # type: ignore[arg-type]
        searcher,  # type: ignore[arg-type]
        model,
        checkpointer=MemoryCheckpointer(),
    )
    app = create_app(ask_agent=agent)
    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as tc:
        yield tc


def _events(body: str) -> list[tuple[str, dict[str, object]]]:
    events: list[tuple[str, dict[str, object]]] = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


# --- Status and disabled AI ---


def test_status_when_ai_is_disabled(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = client.get("/ask/status", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {"enabled": False}


def test_status_when_ai_is_enabled(
    ask_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    assert ask_client.get("/ask/status", headers=auth_headers).json() == {"enabled": True}


def test_status_requires_login(client: TestClient) -> None:
    assert client.get("/ask/status").status_code == 401


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/ask/threads"),
        ("POST", "/ask/threads"),
        ("GET", f"/ask/threads/{uuid.uuid4()}"),
        ("DELETE", f"/ask/threads/{uuid.uuid4()}"),
    ],
)
def test_threads_are_unavailable_when_ai_is_disabled(
    client: TestClient,
    auth_headers: dict[str, str],
    method: str,
    path: str,
) -> None:
    response = client.request(method, path, headers=auth_headers)

    assert response.status_code == 503


def test_asking_is_unavailable_when_ai_is_disabled(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = client.post(
        f"/ask/threads/{uuid.uuid4()}/messages",
        json={"question": "Hi"},
        headers=auth_headers,
    )

    assert response.status_code == 503


# --- Threads ---


def test_create_and_list_threads(
    ask_client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
) -> None:
    created = ask_client.post("/ask/threads", headers=auth_headers)
    ask_client.post("/ask/threads", headers=other_auth_headers)

    assert created.status_code == 201
    assert created.json()["title"] == ""
    listed = ask_client.get("/ask/threads", headers=auth_headers).json()
    assert [t["id"] for t in listed] == [created.json()["id"]]


def test_new_thread_has_no_messages(
    ask_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    thread_id = ask_client.post("/ask/threads", headers=auth_headers).json()["id"]

    response = ask_client.get(f"/ask/threads/{thread_id}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["messages"] == []
    assert response.json()["thread"]["id"] == thread_id


def test_other_users_threads_are_not_found(
    ask_client: TestClient,
    db_session: Session,
    other_user: User,
    auth_headers: dict[str, str],
) -> None:
    thread = create_thread(db_session, other_user)

    for method, path, body in (
        ("GET", f"/ask/threads/{thread.id}", None),
        ("DELETE", f"/ask/threads/{thread.id}", None),
        ("POST", f"/ask/threads/{thread.id}/messages", {"question": "Hi"}),
    ):
        response = ask_client.request(method, path, json=body, headers=auth_headers)
        assert response.status_code == 404, (method, path)
        assert response.json() == {"detail": "Thread not found"}


def test_delete_thread(
    ask_client: TestClient,
    auth_headers: dict[str, str],
    model: ScriptedChatModel,
) -> None:
    model.script = [AIMessage(content="Hi")]
    thread_id = ask_client.post("/ask/threads", headers=auth_headers).json()["id"]
    ask_client.post(
        f"/ask/threads/{thread_id}/messages",
        json={"question": "Hello"},
        headers=auth_headers,
    )

    response = ask_client.delete(f"/ask/threads/{thread_id}", headers=auth_headers)

    assert response.status_code == 204
    assert ask_client.get("/ask/threads", headers=auth_headers).json() == []
    missing = ask_client.get(f"/ask/threads/{thread_id}", headers=auth_headers)
    assert missing.status_code == 404


# --- Asking ---


def test_ask_streams_the_answer(  # noqa: PLR0913
    ask_client: TestClient,
    db_session: Session,
    test_user: User,
    auth_headers: dict[str, str],
    model: ScriptedChatModel,
    searcher: FakeSearcher,
) -> None:
    notebook = create_notebook(db_session, "Travel", test_user)
    note = create_note(db_session, notebook_id=notebook.id, owner=test_user, title="Rome")
    searcher.hits = [hit(note.id, "Rome", "Colosseum")]
    model.script = [
        tool_call("search_notes", query="trip"),
        AIMessage(content="You saw it."),
    ]
    thread_id = ask_client.post("/ask/threads", headers=auth_headers).json()["id"]

    response = ask_client.post(
        f"/ask/threads/{thread_id}/messages",
        json={"question": "What did I see in Rome?"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _events(response.text)
    assert events[0] == (
        "tool",
        {"name": "search_notes", "status": "start", "input": {"query": "trip"}},
    )
    assert "".join(str(d["text"]) for e, d in events if e == "token") == "You saw it."
    [(_, sources)] = [(e, d) for e, d in events if e == "sources"]
    assert sources["sources"] == [
        {
            "note_id": str(note.id),
            "notebook_id": str(searcher.hits[0].notebook_id),
            "title": "Rome",
            "notebook_name": "Travel",
        },
    ]
    assert events[-1] == ("done", {})


def test_first_question_titles_the_thread_and_is_kept(
    ask_client: TestClient,
    auth_headers: dict[str, str],
    model: ScriptedChatModel,
) -> None:
    model.script = [AIMessage(content="Hello there.")]
    thread_id = ask_client.post("/ask/threads", headers=auth_headers).json()["id"]

    ask_client.post(
        f"/ask/threads/{thread_id}/messages",
        json={"question": "Hi agent"},
        headers=auth_headers,
    )

    detail = ask_client.get(f"/ask/threads/{thread_id}", headers=auth_headers).json()
    assert detail["thread"]["title"] == "Hi agent"
    assert detail["messages"] == [
        {"role": "user", "content": "Hi agent", "sources": []},
        {"role": "assistant", "content": "Hello there.", "sources": []},
    ]


def test_model_failure_is_streamed_as_an_error(
    ask_client: TestClient,
    auth_headers: dict[str, str],
    model: ScriptedChatModel,
) -> None:
    model.error = RuntimeError("no credits")
    thread_id = ask_client.post("/ask/threads", headers=auth_headers).json()["id"]

    response = ask_client.post(
        f"/ask/threads/{thread_id}/messages",
        json={"question": "Hi"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert _events(response.text) == [
        ("error", {"message": "Something went wrong while answering. Try again."}),
        ("done", {}),
    ]


def test_empty_question_is_rejected(
    ask_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    thread_id = ask_client.post("/ask/threads", headers=auth_headers).json()["id"]

    response = ask_client.post(
        f"/ask/threads/{thread_id}/messages",
        json={"question": ""},
        headers=auth_headers,
    )

    assert response.status_code == 422
