"""Chat TUI application for the Ask AI agent."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from rich.markup import escape
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.message import Message
from textual.widgets import Input, RichLog

from assistant.agents.rag import ErrorEvent, SourcesEvent, TokenEvent, ToolEvent

if TYPE_CHECKING:
    import uuid
    from collections.abc import Callable

    from textual._path import CSSPathType

    from assistant.agents.rag import AskAgent, AskEvent, ChatMessage
    from assistant.agents.tools import Source


def format_sources(sources: list[Source]) -> str | None:
    """A dim line listing the notes an answer used, or None if there are none."""
    if not sources:
        return None
    titles = ", ".join(escape(f"{s['title']} ({s['notebook_name']})") for s in sources)
    return f"[dim]Sources: {titles}[/dim]"


def format_history_message(message: ChatMessage) -> list[str]:
    """Log lines for one stored message."""
    label = "User" if message.role == "user" else "Assistant"
    lines = [f"[bold]{label}:[/bold] {escape(message.content)}"]
    sources = format_sources(message.sources)
    if sources:
        lines.append(sources)
    return lines


def format_tool_event(event: ToolEvent) -> str | None:
    """A dim line for a tool call starting; finished calls are not shown."""
    if event.status != "start":
        return None
    args = ", ".join(f"{key}={value!r}" for key, value in event.input.items())
    return f"[dim]→ {escape(event.name)}({escape(args)})[/dim]"


class StreamChunk(Message):
    """Message sent from the worker when a line of output is ready."""

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
    """Textual chat app that asks the Ask AI agent and shows its answers.

    The app shows a scrollable log for the conversation and an input at the bottom.
    Long lines in the log wrap at the container width. Use Up/Down and Page Up/Down
    to scroll the message area (works regardless of focus). The chat CLI runs with
    mouse=False so the terminal handles the mouse for text selection and copy.
    Tool calls are shown as they happen; the answer is shown once complete,
    followed by the notes it used. Exit with Ctrl+Q.
    """

    CSS_PATH: ClassVar[CSSPathType | None] = "chat.css"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+up", "log_scroll_up", "Scroll log up", show=False),
        Binding("ctrl+down", "log_scroll_down", "Scroll log down", show=False),
        Binding("ctrl+l", "toggle_focus", "Toggle focus", show=False),
    ]

    def __init__(
        self,
        thread_id: uuid.UUID,
        user_id: uuid.UUID,
        agent: AskAgent,
        *,
        on_question: Callable[[str], None] | None = None,
    ) -> None:
        """Initialize the chat app.

        Args:
            thread_id: The conversation thread (a `ChatThread` of the user).
            user_id: The user asking.
            agent: The Ask AI agent.
            on_question: Called with each question before it is asked (e.g.
                to record it on the thread).
        """
        super().__init__()
        self._chat_thread_id = thread_id
        self._chat_user_id = user_id
        self._agent = agent
        self._on_question = on_question

    def compose(self) -> ComposeResult:
        """Compose the layout: log area and input."""
        yield RichLog(id="log", highlight=True, markup=True, wrap=True)
        yield Input(id="input", placeholder="Ask about your notes...")

    def action_log_scroll_up(self) -> None:
        """Scroll the chat log up by one line."""
        log_widget = self.query_one("#log", RichLog)
        scroll_x, scroll_y = log_widget.scroll_offset
        log_widget.scroll_to(scroll_x, max(scroll_y - 1, 0), animate=False)

    def action_log_scroll_down(self) -> None:
        """Scroll the chat log down by one line."""
        log_widget = self.query_one("#log", RichLog)
        scroll_x, scroll_y = log_widget.scroll_offset
        log_widget.scroll_to(scroll_x, scroll_y + 1, animate=False)

    def action_toggle_focus(self) -> None:
        """Toggle focus between the chat log (read mode) and the input (chat mode)."""
        focused = self.focused
        if isinstance(focused, RichLog):
            self.query_one("#input", Input).focus()
        else:
            self.query_one("#log", RichLog).focus()

    def on_mount(self) -> None:
        """Show the stored conversation and focus the input."""
        for message in self._agent.history(self._chat_thread_id):
            for line in format_history_message(message):
                self.post_message(StreamChunk(line))
        self.query_one("#input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """On enter: run the query in a worker and stream results to the log."""
        value = event.value
        if not value or not value.strip():
            return
        event.input.value = ""
        input_widget = self.query_one("#input", Input)
        log_widget = self.query_one("#log", RichLog)
        input_widget.disabled = True
        log_widget.write(f"[bold]User:[/bold] {escape(value)}", expand=True)
        self.run_worker(
            lambda: self._stream_query(value),
            thread=True,
            exit_on_error=False,
        )

    def _stream_query(self, query: str) -> None:
        """Run in a worker: ask the agent and post its output to the app."""
        try:
            if self._on_question is not None:
                self._on_question(query)
            answer: list[str] = []
            for event in self._agent.stream(
                self._chat_thread_id, self._chat_user_id, query
            ):
                self._handle(event, answer)
        except Exception as e:
            self.post_message(QueryError(str(e)))
        self.post_message(QueryDone())

    def _handle(self, event: AskEvent, answer: list[str]) -> None:
        if isinstance(event, TokenEvent):
            answer.append(event.text)
        elif isinstance(event, ToolEvent):
            line = format_tool_event(event)
            if line:
                self.post_message(StreamChunk(line))
        elif isinstance(event, SourcesEvent):
            text = "".join(answer).strip()
            if text:
                self.post_message(StreamChunk(f"[bold]Assistant:[/bold] {escape(text)}"))
            sources = format_sources(event.sources)
            if sources:
                self.post_message(StreamChunk(sources))
        elif isinstance(event, ErrorEvent):
            self.post_message(QueryError(event.message))

    def on_stream_chunk(self, event: StreamChunk) -> None:
        """Append a line to the log."""
        self.query_one("#log", RichLog).write(event.text, expand=True)

    def on_query_done(self, _event: QueryDone) -> None:
        """Re-enable and focus the input after the agent finishes."""
        input_widget = self.query_one("#input", Input)
        input_widget.disabled = False
        input_widget.focus()

    def on_query_error(self, event: QueryError) -> None:
        """Append an error line to the log."""
        log = self.query_one("#log", RichLog)
        log.write(f"[red]Error:[/red] {escape(event.error)}", expand=True)
