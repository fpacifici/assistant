"""Chat TUI application for the RAG agent."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.message import Message
from textual.widgets import Input, RichLog

if TYPE_CHECKING:
    from langchain_core.messages import BaseMessage

    from assistant.agents.rag import SearchAgent


def _format_message(msg: "BaseMessage") -> str:  # noqa: UP037
    """Format a BaseMessage for display in the chat log.

    Args:
        msg: A langchain BaseMessage (e.g. AIMessage, HumanMessage).

    Returns:
        A string with a short role label and the message content.
    """
    content = getattr(msg, "content", str(msg))
    if not isinstance(content, str):
        content = str(content)
    type_name = type(msg).__name__
    if "Human" in type_name or "user" in type_name.lower():
        label = "User"
    elif "AI" in type_name or "assistant" in type_name.lower():
        label = "Assistant"
    else:
        label = type_name.replace("Message", "")
    return f"[bold]{label}:[/bold] {content}"


class StreamChunk(Message):
    """Message sent from the worker when a streamed message chunk is ready."""

    def __init__(self, text: str) -> None:
        self.text = text
        super().__init__()


class QueryDone(Message):
    """Message sent when the agent has finished streaming a response."""


class QueryError(Message):
    """Message sent when the agent or stream raised an error."""

    def __init__(self, error: str) -> None:
        self.error = error
        super().__init__()


class ChatApp(App[None]):
    """Textual chat app that sends user queries to the RAG agent and streams responses.

    The app shows a scrollable log for the conversation and an input at the bottom.
    Long lines in the log wrap at the container width. Use Up/Down and Page Up/Page Down
    to scroll the message area (works regardless of focus). The chat CLI runs with
    mouse=False so the terminal handles the mouse for text selection and copy.
    Submit a query to stream agent messages; when done, you can send another.
    Exit with Ctrl+Q.
    """

    CSS_PATH = "chat.css"

    BINDINGS = [
        Binding("up", "scroll_log_up", "Scroll Up", show=False),
        Binding("down", "scroll_log_down", "Scroll Down", show=False),
        Binding("pageup", "scroll_log_page_up", "Page Up", show=False),
        Binding("pagedown", "scroll_log_page_down", "Page Down", show=False),
    ]

    def __init__(self, thread_id: str, agent: SearchAgent) -> None:
        """Initialize the chat app.

        Args:
            thread_id: Conversation thread ID passed to the agent.
            agent: RAG SearchAgent used for query().
        """
        super().__init__()
        self._rag_thread_id = thread_id
        self._rag_agent = agent

    def compose(self) -> ComposeResult:
        """Compose the layout: log area and input."""
        with VerticalScroll(id="log-container"):
            yield RichLog(id="log", highlight=True, markup=True, wrap=True)
        yield Input(id="input", placeholder="Send a query...")

    def on_mount(self) -> None:
        """Focus the input when the app mounts."""
        self.query_one("#input", Input).focus()

    def _scroll_container(self) -> VerticalScroll:
        """Return the log scroll container for keyboard scrolling."""
        return self.query_one("#log-container", VerticalScroll)

    def action_scroll_log_up(self) -> None:
        """Scroll the message log up one line."""
        self._scroll_container().scroll_up()

    def action_scroll_log_down(self) -> None:
        """Scroll the message log down one line."""
        self._scroll_container().scroll_down()

    def action_scroll_log_page_up(self) -> None:
        """Scroll the message log up one page."""
        self._scroll_container().page_up()

    def action_scroll_log_page_down(self) -> None:
        """Scroll the message log down one page."""
        self._scroll_container().page_down()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """On enter: run the query in a worker and stream results to the log."""
        value = event.value
        if not value or not value.strip():
            return
        event.input.value = ""
        input_widget = self.query_one("#input", Input)
        log_widget = self.query_one("#log", RichLog)
        input_widget.disabled = True
        log_widget.write(f"[bold]User:[/bold] {value}", expand=True)
        self.run_worker(
            lambda: self._stream_query(value),
            thread=True,
            exit_on_error=False,
        )

    def _stream_query(self, query: str) -> None:
        """Run in a worker: call agent.query and post each message to the app."""
        try:
            for msg in self._rag_agent.query(self._rag_thread_id, query):
                text = _format_message(msg)
                self.post_message(StreamChunk(text))
            self.post_message(QueryDone())
        except Exception as e:
            self.post_message(QueryError(str(e)))
            self.post_message(QueryDone())

    def on_stream_chunk(self, event: StreamChunk) -> None:
        """Append a streamed message chunk to the log."""
        self.query_one("#log", RichLog).write(event.text, expand=True)

    def on_query_done(self, _event: QueryDone) -> None:
        """Re-enable and focus the input after the agent finishes."""
        input_widget = self.query_one("#input", Input)
        input_widget.disabled = False
        input_widget.focus()

    def on_query_error(self, event: QueryError) -> None:
        """Append an error line to the log."""
        self.query_one("#log", RichLog).write(f"[red]Error:[/red] {event.error}", expand=True)
