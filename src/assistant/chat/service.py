"""Ask AI threads: create, list, rename on first question, delete.

A thread belongs to one user and is only ever visible to them; another
user's thread looks exactly like a missing one. The conversation itself is
stored by the agent's langgraph checkpointer under the thread id (see
`assistant.agents.rag`), so deleting a thread here must be followed by
`AskAgent.delete_history`.

Like the notes service, these functions flush but never commit.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from assistant.chat.exceptions import ChatThreadNotFoundError
from assistant.models.schema import ChatThread

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session

    from assistant.models.schema import User

TITLE_MAX_LENGTH = 80


def title_from_question(question: str) -> str:
    """A thread title: the first question on one line, shortened if long."""
    title = " ".join(question.split())
    if len(title) <= TITLE_MAX_LENGTH:
        return title
    return title[: TITLE_MAX_LENGTH - 1].rstrip() + "…"


def create_thread(session: Session, user: User) -> ChatThread:
    """Start an empty thread for `user`."""
    thread = ChatThread(user_id=user.uid)
    session.add(thread)
    session.flush()
    return thread


def get_thread(session: Session, user: User, thread_id: uuid.UUID) -> ChatThread:
    """Return the user's thread.

    Raises:
        ChatThreadNotFoundError: If it does not exist or is someone else's.
    """
    thread = session.get(ChatThread, thread_id)
    if thread is None or thread.user_id != user.uid:
        raise ChatThreadNotFoundError(str(thread_id))
    return thread


def list_threads(
    session: Session,
    user: User,
    *,
    offset: int = 0,
    limit: int | None = None,
) -> list[ChatThread]:
    """The user's threads, most recently used first."""
    stmt = (
        select(ChatThread)
        .where(ChatThread.user_id == user.uid)
        .order_by(ChatThread.updated_at.desc(), ChatThread.id)
        .offset(offset)
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt))


def record_question(
    session: Session,
    user: User,
    thread_id: uuid.UUID,
    question: str,
) -> ChatThread:
    """Note that a question is being asked in a thread.

    Bumps `updated_at`; the first question also becomes the title.

    Raises:
        ChatThreadNotFoundError: If the thread is not the user's.
    """
    thread = get_thread(session, user, thread_id)
    if not thread.title:
        thread.title = title_from_question(question)
    thread.updated_at = datetime.now(UTC)
    session.flush()
    return thread


def delete_thread(session: Session, user: User, thread_id: uuid.UUID) -> None:
    """Delete the user's thread row.

    Raises:
        ChatThreadNotFoundError: If the thread is not the user's.
    """
    thread = get_thread(session, user, thread_id)
    session.delete(thread)
    session.flush()
