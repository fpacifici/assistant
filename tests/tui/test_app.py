"""Tests for the chat TUI app and the chat/query CLIs."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from assistant.agents.rag import (
    ChatMessage,
    DoneEvent,
    ErrorEvent,
    SourcesEvent,
    TokenEvent,
    ToolEvent,
)
from assistant.chat.service import create_thread
from assistant.cli.chat import main as chat_main
from assistant.cli.query import main as query_main
from assistant.models.schema import ChatThread, User
from assistant.tui.app import (
    ChatApp,
    format_history_message,
    format_sources,
    format_tool_event,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager

    from sqlalchemy.orm import Session

_SOURCE = {"note_id": "1", "notebook_id": "2", "title": "Rome", "notebook_name": "Travel"}


# --- Formatting ---


def test_format_history_messages() -> None:
    assert format_history_message(ChatMessage(role="user", content="Where?")) == [
        "[bold]User:[/bold] Where?",
    ]
    assert format_history_message(
        ChatMessage(role="assistant", content="Rome", sources=[_SOURCE]),  # type: ignore[list-item]
    ) == ["[bold]Assistant:[/bold] Rome", "[dim]Sources: Rome (Travel)[/dim]"]


def test_markup_in_content_is_escaped() -> None:
    [line] = format_history_message(ChatMessage(role="user", content="[red]x"))

    assert line == "[bold]User:[/bold] \\[red]x"


def test_format_tool_event() -> None:
    start = ToolEvent(name="search_notes", status="start", input={"query": "rome"})

    assert format_tool_event(start) == "[dim]→ search_notes(query='rome')[/dim]"
    assert format_tool_event(ToolEvent(name="search_notes", status="end")) is None


def test_format_sources_without_sources() -> None:
    assert format_sources([]) is None


# --- App ---


def test_chat_app_has_log_scroll_and_focus_bindings() -> None:
    binding_keys = {binding.key for binding in ChatApp.BINDINGS}
    assert {"ctrl+up", "ctrl+down", "ctrl+l"} <= binding_keys


def test_stream_query_posts_tools_then_answer_and_sources() -> None:
    agent = MagicMock()
    agent.stream.return_value = iter(
        [
            ToolEvent(name="search_notes", status="start", input={"query": "q"}),
            ToolEvent(name="search_notes", status="end"),
            TokenEvent(text="In "),
            TokenEvent(text="Rome."),
            SourcesEvent(sources=[_SOURCE]),  # type: ignore[list-item]
            DoneEvent(),
        ],
    )
    asked: list[str] = []
    thread_id, user_id = uuid.uuid4(), uuid.uuid4()
    app = ChatApp(thread_id, user_id, agent, on_question=asked.append)

    with patch.object(app, "post_message") as post:
        app._stream_query("Where?")

    agent.stream.assert_called_once_with(thread_id, user_id, "Where?")
    assert asked == ["Where?"]
    posted = [
        getattr(call.args[0], "text", type(call.args[0]).__name__)
        for call in post.call_args_list
    ]
    assert posted == [
        "[dim]→ search_notes(query='q')[/dim]",
        "[bold]Assistant:[/bold] In Rome.",
        "[dim]Sources: Rome (Travel)[/dim]",
        "QueryDone",
    ]


def test_stream_query_posts_errors() -> None:
    agent = MagicMock()
    agent.stream.return_value = iter([ErrorEvent(message="No credits"), DoneEvent()])
    app = ChatApp(uuid.uuid4(), uuid.uuid4(), agent)

    with patch.object(app, "post_message") as post:
        app._stream_query("Where?")

    messages = [call.args[0] for call in post.call_args_list]
    assert messages[0].error == "No credits"
    assert type(messages[1]).__name__ == "QueryDone"


# --- CLIs ---


@pytest.fixture
def alice(db_session: Session) -> User:
    user = User(email="alice@test.com", firstname="A", lastname="B")
    db_session.add(user)
    db_session.flush()
    return user


def _patched_factory(
    factory: Callable[[], AbstractContextManager[Session]],
) -> MagicMock:
    return MagicMock(return_value=factory)


def test_chat_cli_starts_a_new_thread(
    db_session: Session,
    db_session_factory: Callable[[], AbstractContextManager[Session]],
    alice: User,
) -> None:
    agent = MagicMock()
    with (
        patch(
            "assistant.cli.chat.get_session_factory", _patched_factory(db_session_factory)
        ),
        patch("assistant.cli.chat.create_ask_agent", return_value=agent),
        patch("assistant.cli.chat.ChatApp") as app_cls,
        patch("sys.argv", ["chat", "--email", alice.email]),
    ):
        assert chat_main() == 0

    [thread] = db_session.query(ChatThread).all()
    assert thread.user_id == alice.uid
    args = app_cls.call_args
    assert args.args == (thread.id, alice.uid, agent)
    app_cls.return_value.run.assert_called_once_with(mouse=False)

    # Questions asked in the app are recorded on the thread.
    args.kwargs["on_question"]("First question")
    assert thread.title == "First question"


def test_chat_cli_resumes_a_thread(
    db_session: Session,
    db_session_factory: Callable[[], AbstractContextManager[Session]],
    alice: User,
) -> None:
    thread = create_thread(db_session, alice)
    with (
        patch(
            "assistant.cli.chat.get_session_factory", _patched_factory(db_session_factory)
        ),
        patch("assistant.cli.chat.create_ask_agent", return_value=MagicMock()),
        patch("assistant.cli.chat.ChatApp") as app_cls,
        patch(
            "sys.argv", ["chat", "--email", alice.email, "--thread-id", str(thread.id)]
        ),
    ):
        assert chat_main() == 0

    assert app_cls.call_args.args[0] == thread.id


def test_chat_cli_needs_ai(
    db_session_factory: Callable[[], AbstractContextManager[Session]],
) -> None:
    with (
        patch(
            "assistant.cli.chat.get_session_factory", _patched_factory(db_session_factory)
        ),
        patch("sys.argv", ["chat", "--email", "a@test.com"]),
    ):
        assert chat_main() == 1


def test_chat_cli_unknown_user(
    db_session_factory: Callable[[], AbstractContextManager[Session]],
) -> None:
    with (
        patch(
            "assistant.cli.chat.get_session_factory", _patched_factory(db_session_factory)
        ),
        patch("assistant.cli.chat.create_ask_agent", return_value=MagicMock()),
        patch("sys.argv", ["chat", "--email", "nobody@test.com"]),
    ):
        assert chat_main() == 1


def test_query_cli_prints_the_answer(
    db_session_factory: Callable[[], AbstractContextManager[Session]],
    alice: User,
    capsys: pytest.CaptureFixture[str],
) -> None:
    agent = MagicMock()
    agent.stream.return_value = iter(
        [
            ToolEvent(name="search_notes", status="start", input={"query": "q"}),
            TokenEvent(text="In Rome."),
            SourcesEvent(sources=[_SOURCE]),  # type: ignore[list-item]
            DoneEvent(),
        ],
    )
    with (
        patch(
            "assistant.cli.query.get_session_factory",
            _patched_factory(db_session_factory),
        ),
        patch("assistant.cli.query.create_ask_agent", return_value=agent),
        patch("sys.argv", ["query", "--email", alice.email, "Where?"]),
    ):
        assert query_main() == 0

    out, err = capsys.readouterr()
    assert out == "In Rome.\n"
    assert "search_notes" in err
    assert "Source: Rome (1)" in err


def test_query_cli_fails_on_error_events(
    db_session_factory: Callable[[], AbstractContextManager[Session]],
    alice: User,
) -> None:
    agent = MagicMock()
    agent.stream.return_value = iter([ErrorEvent(message="No credits"), DoneEvent()])
    with (
        patch(
            "assistant.cli.query.get_session_factory",
            _patched_factory(db_session_factory),
        ),
        patch("assistant.cli.query.create_ask_agent", return_value=agent),
        patch("sys.argv", ["query", "--email", alice.email, "Where?"]),
    ):
        assert query_main() == 1
