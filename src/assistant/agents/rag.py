"""The Ask AI agent: answers questions from the notes a user can view.

A langchain `create_agent` agent with three tools (`assistant.agents.tools`)
bound to the asking user. Conversations are multi-turn: the langgraph
checkpointer (`PostgresSaver`) stores each thread's messages under the
`ChatThread` id.

`AskAgent.stream` turns the agent's run into a flat sequence of `AskEvent`s
(answer tokens, tool calls, the notes used, errors) that the API sends as
server-sent events and the terminal chat prints. A failure of the model
(no credits, rate limits, outage) ends the stream with an `ErrorEvent`
instead of raising.

Runs are traced to LangSmith when it is configured (see
`assistant.agents.tracing`), tagged with the user and thread ids.
"""

from __future__ import annotations

import json
import logging
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

import openai
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres import PostgresSaver

from assistant.agents.tools import Source, build_tools, unique_sources
from assistant.config import Config
from assistant.models.database import get_database_url
from assistant.vectors.search import NoteSearcher

if TYPE_CHECKING:
    import uuid
    from collections.abc import Callable, Iterator, Sequence
    from contextlib import AbstractContextManager

    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import BaseMessage
    from langgraph.checkpoint.base import BaseCheckpointSaver
    from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are the assistant of a note-taking app. You answer the user's questions \
using their notes, which you can only reach through your tools.

- Always search before answering: search_notes finds passages by meaning, \
keyword_search finds exact names, words and phrases, get_note reads a whole \
note.
- Answer only from what the tools return. If the notes don't contain the \
answer, say that you could not find it in the notes. Never make up facts.
- Mention the titles of the notes you used.
- Be concise. Answer in the language of the question, in markdown.

Today is {today}."""

# --- Events ---


@dataclass(frozen=True, slots=True)
class TokenEvent:
    """A piece of the answer text."""

    text: str
    type: Literal["token"] = "token"


@dataclass(frozen=True, slots=True)
class ToolEvent:
    """The agent started or finished calling a tool."""

    name: str
    status: Literal["start", "end"]
    input: dict[str, Any] = field(default_factory=dict)
    type: Literal["tool"] = "tool"


@dataclass(frozen=True, slots=True)
class SourcesEvent:
    """The notes the tools returned while answering."""

    sources: list[Source]
    type: Literal["sources"] = "sources"


@dataclass(frozen=True, slots=True)
class ErrorEvent:
    """Answering failed; `message` is safe to show to the user."""

    message: str
    type: Literal["error"] = "error"


@dataclass(frozen=True, slots=True)
class DoneEvent:
    """The stream is over."""

    type: Literal["done"] = "done"


AskEvent = TokenEvent | ToolEvent | SourcesEvent | ErrorEvent | DoneEvent


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """One message of a stored conversation, as shown to the user."""

    role: Literal["user", "assistant"]
    content: str
    sources: list[Source] = field(default_factory=list)


# --- Checkpointer ---

_setup_lock = threading.Lock()
_setup_done = False


@contextmanager
def postgres_checkpointer() -> Iterator[BaseCheckpointSaver[Any]]:
    """A `PostgresSaver` on the app database; creates its tables on first use."""
    global _setup_done  # noqa: PLW0603
    with PostgresSaver.from_conn_string(get_database_url()) as checkpointer:
        with _setup_lock:
            if not _setup_done:
                checkpointer.setup()
                _setup_done = True
        yield checkpointer


# --- Helpers ---


def message_text(message: BaseMessage) -> str:
    """The text of a message, whether its content is a string or parts."""
    content = message.content
    if isinstance(content, str):
        return content
    return "".join(
        part["text"]
        for part in content
        if isinstance(part, dict) and part.get("type") == "text" and "text" in part
    )


def error_message(exc: BaseException) -> str:
    """What to tell the user when answering failed."""
    if isinstance(exc, openai.RateLimitError):
        if "insufficient_quota" in str(exc):
            return "The AI service has no credits left. Ask the administrator."
        return "The AI service is busy. Try again in a minute."
    if isinstance(exc, openai.APIError):
        return "The AI service is unavailable right now. Try again later."
    return "Something went wrong while answering. Try again."


def history_from_messages(messages: Sequence[BaseMessage]) -> list[ChatMessage]:
    """Turn stored agent messages into the conversation shown to the user.

    Tool calls and tool results are hidden; the notes a tool returned are
    attached, as sources, to the answer that followed.
    """
    history: list[ChatMessage] = []
    pending: list[Source] = []
    for message in messages:
        if isinstance(message, HumanMessage):
            history.append(ChatMessage(role="user", content=message_text(message)))
            pending = []
        elif isinstance(message, ToolMessage):
            if isinstance(message.artifact, list):
                pending.extend(message.artifact)
        elif isinstance(message, AIMessage) and not message.tool_calls:
            text = message_text(message)
            if text:
                history.append(
                    ChatMessage(
                        role="assistant",
                        content=text,
                        sources=unique_sources(pending),
                    ),
                )
                pending = []
    return history


# --- Agent ---


class AskAgent:
    """Answers questions about a user's notes, one thread at a time."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        searcher: NoteSearcher,
        chat_model: str | BaseChatModel,
        *,
        checkpointer: Callable[
            [],
            AbstractContextManager[BaseCheckpointSaver[Any]],
        ] = postgres_checkpointer,
    ) -> None:
        """Create the agent.

        Args:
            session_factory: Sessions for the tools.
            searcher: Semantic search over note chunks.
            chat_model: A langchain `provider:model` string or a chat model.
            checkpointer: Opens the store of conversations.
        """
        self._session_factory = session_factory
        self._searcher = searcher
        self._chat_model = chat_model
        self._checkpointer = checkpointer

    def _build(self, checkpointer: BaseCheckpointSaver[Any], user_id: uuid.UUID) -> Any:  # noqa: ANN401
        return create_agent(
            self._chat_model,
            build_tools(self._session_factory, user_id, self._searcher),
            system_prompt=SYSTEM_PROMPT.format(
                today=datetime.now(UTC).date().isoformat()
            ),
            checkpointer=checkpointer,
        )

    def stream(
        self,
        thread_id: uuid.UUID,
        user_id: uuid.UUID,
        question: str,
    ) -> Iterator[AskEvent]:
        """Ask a question in a thread and stream the answer.

        The caller must have checked that the thread belongs to the user.

        Yields:
            Tokens and tool events as they happen, then the sources, then
            `DoneEvent`. On failure an `ErrorEvent` replaces the sources.
        """
        config = RunnableConfig(
            configurable={"thread_id": str(thread_id)},
            metadata={"user_id": str(user_id), "thread_id": str(thread_id)},
            tags=["ask"],
            run_name="ask",
        )
        sources: list[Source] = []
        try:
            with self._checkpointer() as checkpointer:
                agent = self._build(checkpointer, user_id)
                for mode, data in agent.stream(
                    {"messages": [{"role": "user", "content": question}]},
                    config,
                    stream_mode=["messages", "updates"],
                ):
                    if mode == "messages":
                        yield from _token_events(data)
                    else:
                        yield from _update_events(data, sources)
        except Exception as exc:
            logger.exception("Ask AI failed (thread %s)", thread_id)
            yield ErrorEvent(message=error_message(exc))
        else:
            yield SourcesEvent(sources=unique_sources(sources))
        yield DoneEvent()

    def history(self, thread_id: uuid.UUID) -> list[ChatMessage]:
        """The stored conversation of a thread (empty for a new thread)."""
        with self._checkpointer() as checkpointer:
            checkpoint = checkpointer.get_tuple(
                RunnableConfig(configurable={"thread_id": str(thread_id)}),
            )
        if checkpoint is None:
            return []
        messages = checkpoint.checkpoint["channel_values"].get("messages", [])
        return history_from_messages(messages)

    def delete_history(self, thread_id: uuid.UUID) -> None:
        """Delete the stored conversation of a thread."""
        with self._checkpointer() as checkpointer:
            checkpointer.delete_thread(str(thread_id))


def _token_events(data: Any) -> Iterator[AskEvent]:  # noqa: ANN401
    message, metadata = data
    if (
        isinstance(message, AIMessageChunk)
        and isinstance(metadata, dict)
        and metadata.get("langgraph_node") == "model"
    ):
        text = message_text(message)
        if text:
            yield TokenEvent(text=text)


def _update_events(data: Any, sources: list[Source]) -> Iterator[AskEvent]:  # noqa: ANN401
    if not isinstance(data, dict):
        return
    for update in data.values():
        if not isinstance(update, dict):
            continue
        for message in update.get("messages", []):
            if isinstance(message, AIMessage):
                for call in message.tool_calls:
                    yield ToolEvent(name=call["name"], status="start", input=call["args"])
            elif isinstance(message, ToolMessage):
                yield ToolEvent(name=message.name or "", status="end")
                if isinstance(message.artifact, list):
                    sources.extend(message.artifact)


def create_ask_agent(
    session_factory: sessionmaker[Session],
    config: Config | None = None,
) -> AskAgent | None:
    """Build the agent from config, or `None` when AI is disabled."""
    ai_config = (config or Config()).get_ai_config()
    if not ai_config["enabled"]:
        return None
    from langchain_openai import OpenAIEmbeddings  # noqa: PLC0415

    searcher = NoteSearcher(OpenAIEmbeddings(model=ai_config["embedding_model"]))
    return AskAgent(session_factory, searcher, ai_config["chat_model"])


def event_payload(event: AskEvent) -> str:
    """The JSON body of an event, as sent to clients."""
    if isinstance(event, TokenEvent):
        body: dict[str, Any] = {"text": event.text}
    elif isinstance(event, ToolEvent):
        body = {"name": event.name, "status": event.status, "input": event.input}
    elif isinstance(event, SourcesEvent):
        body = {"sources": event.sources}
    elif isinstance(event, ErrorEvent):
        body = {"message": event.message}
    else:
        body = {}
    return json.dumps(body)
