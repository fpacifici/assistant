"""Tests for the chat TUI app and CLI."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from assistant.cli.chat import main as chat_main
from assistant.tui.app import ChatApp, _format_message


def test_format_message_ai_content() -> None:
    """Test that _format_message returns label and content for AI-like message."""
    msg = MagicMock(spec=["content", "__class__"])
    msg.content = "Hello from the assistant."
    msg.__class__.__name__ = "AIMessage"
    assert _format_message(msg) == "[bold]Assistant:[/bold] Hello from the assistant."


def test_format_message_human_content() -> None:
    """Test that _format_message returns User label for human-like message."""
    msg = MagicMock(spec=["content", "__class__"])
    msg.content = "What is the weather?"
    msg.__class__.__name__ = "HumanMessage"
    assert _format_message(msg) == "[bold]User:[/bold] What is the weather?"


def test_format_message_tool_message() -> None:
    """Test that _format_message uses Tool label for tool messages."""
    msg = MagicMock(spec=["content", "__class__"])
    msg.content = "tool result"
    msg.__class__.__name__ = "ToolMessage"
    assert _format_message(msg) == "[bold]Tool:[/bold] tool result"


def test_chat_app_constructs_with_thread_id_and_agent() -> None:
    """Test that ChatApp can be constructed with thread_id and mock agent."""
    mock_agent = MagicMock()
    app = ChatApp(thread_id="test-thread-123", agent=mock_agent)
    assert app._rag_thread_id == "test-thread-123"
    assert app._rag_agent is mock_agent


def test_chat_app_has_log_scroll_and_focus_bindings() -> None:
    """Test that ChatApp defines expected key bindings for log and input."""
    binding_keys = {binding.key for binding in ChatApp.BINDINGS}
    assert "ctrl+up" in binding_keys
    assert "ctrl+down" in binding_keys
    assert "ctrl+l" in binding_keys


def test_chat_cli_parses_thread_id() -> None:
    """Test that the chat CLI parses thread_id and runs the app."""
    with (
        patch("assistant.cli.chat.init_environment") as mock_init,
        patch("assistant.cli.chat.SearchAgent") as mock_agent_cls,
        patch("assistant.cli.chat.ChatApp") as mock_app_cls,
        patch("sys.argv", ["chat", "my-thread-id"]),
    ):
        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent
        mock_app = MagicMock()
        mock_app_cls.return_value = mock_app
        result = chat_main()
    assert result == 0
    mock_init.assert_called_once()
    mock_agent_cls.assert_called_once()
    mock_app_cls.assert_called_once_with(thread_id="my-thread-id", agent=mock_agent)
    mock_app.run.assert_called_once()


def test_chat_cli_returns_one_on_exception() -> None:
    """Test that the chat CLI returns 1 when an exception occurs."""
    with (
        patch("assistant.cli.chat.init_environment"),
        patch("assistant.cli.chat.SearchAgent") as mock_agent_cls,
        patch("sys.argv", ["chat", "thread-1"]),
    ):
        mock_agent_cls.side_effect = RuntimeError("test error")
        result = chat_main()
    assert result == 1
