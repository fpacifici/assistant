"""Ask AI routes: the user's threads and streamed answers.

Answers are streamed as server-sent events (`text/event-stream`), one event
per `assistant.agents.rag.AskEvent`:

    event: token     data: {"text": "..."}
    event: tool      data: {"name": "search_notes", "status": "start", "input": {...}}
    event: sources   data: {"sources": [{"note_id", "notebook_id", "title",
                                         "notebook_name"}, ...]}
    event: error     data: {"message": "..."}
    event: done      data: {}

A model failure (e.g. no credits) is an `error` event, not an HTTP error.
Every route but `/status` answers 503 when AI is disabled.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from assistant.agents.rag import AskAgent, event_payload
from assistant.api.dependencies import CurrentUser, CurrentUserId, SessionDep
from assistant.api.schemas.ask import (
    AskRequest,
    AskStatusResponse,
    ChatMessageResponse,
    ChatThreadDetailResponse,
    ChatThreadResponse,
)
from assistant.api.schemas.pagination import Pagination
from assistant.chat.exceptions import AIDisabledError
from assistant.chat.service import (
    create_thread,
    delete_thread,
    get_thread,
    list_threads,
    record_question,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

router = APIRouter()


def get_ask_agent(request: Request) -> AskAgent:
    """The app's agent; 503 (`AIDisabledError`) when AI is disabled."""
    agent: AskAgent | None = request.app.state.ask_agent
    if agent is None:
        raise AIDisabledError
    return agent


AskAgentDep = Annotated[AskAgent, Depends(get_ask_agent)]


@router.get("/status", response_model=AskStatusResponse)
def ask_status(request: Request, _user_id: CurrentUserId) -> AskStatusResponse:
    return AskStatusResponse(enabled=request.app.state.ask_agent is not None)


@router.get("/threads", response_model=list[ChatThreadResponse])
def list_threads_endpoint(
    session: SessionDep,
    user: CurrentUser,
    _agent: AskAgentDep,
    pagination: Pagination,
) -> list[ChatThreadResponse]:
    threads = list_threads(
        session,
        user,
        offset=pagination.offset,
        limit=pagination.limit,
    )
    return [ChatThreadResponse.model_validate(t) for t in threads]


@router.post("/threads", status_code=201, response_model=ChatThreadResponse)
def create_thread_endpoint(
    session: SessionDep,
    user: CurrentUser,
    _agent: AskAgentDep,
) -> ChatThreadResponse:
    return ChatThreadResponse.model_validate(create_thread(session, user))


@router.get("/threads/{thread_id}", response_model=ChatThreadDetailResponse)
def get_thread_endpoint(
    thread_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
    agent: AskAgentDep,
) -> ChatThreadDetailResponse:
    thread = get_thread(session, user, thread_id)
    return ChatThreadDetailResponse(
        thread=ChatThreadResponse.model_validate(thread),
        messages=[
            ChatMessageResponse.model_validate(m) for m in agent.history(thread.id)
        ],
    )


@router.delete("/threads/{thread_id}", status_code=204)
def delete_thread_endpoint(
    thread_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
    agent: AskAgentDep,
) -> None:
    get_thread(session, user, thread_id)
    # Conversation first: if that fails the thread is still listed and the
    # user can retry, rather than leaving an unreachable conversation.
    agent.delete_history(thread_id)
    delete_thread(session, user, thread_id)


@router.post("/threads/{thread_id}/messages")
def ask_endpoint(
    thread_id: uuid.UUID,
    body: AskRequest,
    session: SessionDep,
    user: CurrentUser,
    agent: AskAgentDep,
) -> StreamingResponse:
    record_question(session, user, thread_id, body.question)
    # The stream outlives this request's session; commit the title and
    # timestamp now rather than when the response is done.
    session.commit()
    user_id = user.uid

    def events() -> Iterator[str]:
        for event in agent.stream(thread_id, user_id, body.question):
            yield f"event: {event.type}\ndata: {event_payload(event)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
