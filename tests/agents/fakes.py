"""Test doubles for the Ask AI agent: a scripted chat model and searcher."""

from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langgraph.checkpoint.memory import InMemorySaver

from assistant.vectors.search import ChunkHit

if TYPE_CHECKING:
    from collections.abc import Iterator

    from langchain_core.callbacks import CallbackManagerForLLMRun
    from langchain_core.messages import BaseMessage
    from sqlalchemy.orm import Session

    from assistant.models.schema import User


class ScriptedChatModel(BaseChatModel):
    """Replies with the given messages in order, streaming text word by word.

    A message with tool calls is streamed as one tool-call chunk. Raises
    `error` instead of replying once the script runs out, if set.
    """

    script: list[AIMessage]
    error: Exception | None = None
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> ScriptedChatModel:  # noqa: ANN401, ARG002
        return self

    def _next(self) -> AIMessage:
        if self.calls >= len(self.script):
            if self.error is not None:
                raise self.error
            msg = "The script has no more replies"
            raise AssertionError(msg)
        message = self.script[self.calls]
        self.calls += 1
        return message

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,  # noqa: ANN401
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        return ChatResult(generations=[ChatGeneration(message=self._next())])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,  # noqa: ANN401
    ) -> Iterator[ChatGenerationChunk]:
        del messages, stop, kwargs
        message = self._next()
        if message.tool_calls:
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content="",
                    tool_call_chunks=[
                        {
                            "name": call["name"],
                            "args": json.dumps(call["args"]),
                            "id": call["id"],
                            "index": index,
                        }
                        for index, call in enumerate(message.tool_calls)
                    ],
                ),
            )
            return
        words = str(message.content).split(" ")
        for index, word in enumerate(words):
            text = word if index == len(words) - 1 else word + " "
            chunk = ChatGenerationChunk(message=AIMessageChunk(content=text))
            if run_manager is not None:
                run_manager.on_llm_new_token(text, chunk=chunk)
            yield chunk


def tool_call(name: str, **args: object) -> AIMessage:
    """A model reply that calls one tool."""
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": f"call-{uuid.uuid4().hex[:8]}"}],
    )


class FakeSearcher:
    """A `NoteSearcher` returning fixed hits and recording queries."""

    def __init__(self, hits: list[ChunkHit] | None = None) -> None:
        self.hits = hits or []
        self.queries: list[tuple[uuid.UUID, str]] = []

    def search(
        self, session: Session, user: User, query: str, *, k: int = 6
    ) -> list[ChunkHit]:
        del session
        self.queries.append((user.uid, query))
        return self.hits[:k]


def hit(note_id: uuid.UUID, title: str, content: str = "text") -> ChunkHit:
    """A search hit in notebook "Travel"."""
    return ChunkHit(
        note_id=note_id,
        notebook_id=uuid.uuid4(),
        title=title,
        notebook_name="Travel",
        content=f"Title: {title}\nNotebook: Travel\n\n{content}",
        score=0.1,
    )


class MemoryCheckpointer:
    """A checkpointer factory sharing one in-memory store across calls."""

    def __init__(self) -> None:
        self.saver = InMemorySaver()

    @contextmanager
    def __call__(self) -> Iterator[InMemorySaver]:
        yield self.saver
