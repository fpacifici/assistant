"""LangSmith evaluation target and evaluators for the Ask AI agent.

The target asks each dataset question as the eval user (`EVAL_USER_EMAIL`,
default `eval@assistant.invalid`), in a throwaway thread, and returns the
answer plus the titles and notebooks of the notes the agent's tools
returned.

Evals call the real models: run them by hand (`make eval`), never in CI.
"""

from __future__ import annotations

import functools
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from openevals.llm import create_llm_as_judge
from openevals.prompts import CORRECTNESS_PROMPT

from assistant.agents.rag import (
    AskAgent,
    ErrorEvent,
    SourcesEvent,
    TokenEvent,
    create_ask_agent,
)
from assistant.chat.service import create_thread, delete_thread, record_question
from assistant.models.database import get_session_factory
from assistant.notes.user_service import get_user, get_user_by_email

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session, sessionmaker

DEFAULT_EVAL_USER_EMAIL = "eval@assistant.invalid"
JUDGE_MODEL = "openai:o3-mini"


def eval_user_email() -> str:
    """The user whose notes the evals ask about."""
    return os.getenv("EVAL_USER_EMAIL", DEFAULT_EVAL_USER_EMAIL)


@dataclass(frozen=True, slots=True)
class EvalContext:
    """What the target needs, built once per process."""

    session_factory: sessionmaker[Session]
    agent: AskAgent
    user_id: uuid.UUID


@functools.cache
def _context() -> EvalContext:
    session_factory = get_session_factory()
    agent = create_ask_agent(session_factory)
    if agent is None:
        msg = "AI is disabled: set OPENAI_API_KEY to run the evals"
        raise RuntimeError(msg)
    with session_factory() as session:
        user_id = get_user_by_email(session, eval_user_email()).uid
    return EvalContext(session_factory=session_factory, agent=agent, user_id=user_id)


def ask(context: EvalContext, question: str) -> dict[str, object]:
    """Ask one question in a new thread, then delete the thread.

    Returns:
        `answer` (the text, or the error message), `sources` (note titles
        in the order the tools returned them), `notebooks` and `error`.
    """
    with context.session_factory() as session:
        user = get_user(session, context.user_id)
        thread_id = create_thread(session, user).id
        record_question(session, user, thread_id, question)
        session.commit()

    answer: list[str] = []
    titles: list[str] = []
    notebooks: list[str] = []
    error: str | None = None
    try:
        for event in context.agent.stream(thread_id, context.user_id, question):
            if isinstance(event, TokenEvent):
                answer.append(event.text)
            elif isinstance(event, SourcesEvent):
                titles = [source["title"] for source in event.sources]
                notebooks = list(dict.fromkeys(s["notebook_name"] for s in event.sources))
            elif isinstance(event, ErrorEvent):
                error = event.message
    finally:
        with context.session_factory() as session:
            delete_thread(session, get_user(session, context.user_id), thread_id)
            session.commit()
        context.agent.delete_history(thread_id)

    return {
        "answer": error or "".join(answer).strip(),
        "sources": titles,
        "notebooks": notebooks,
        "error": error,
    }


def target(inputs: dict[str, object]) -> dict[str, object]:
    """LangSmith target: answer `inputs["question"]` as the eval user."""
    return ask(_context(), str(inputs["question"]))


def correctness_evaluator(
    inputs: dict[str, object],
    outputs: dict[str, object],
    reference_outputs: dict[str, object],
) -> object:
    """LLM-as-judge: is the answer correct given the reference answer?"""
    evaluator = create_llm_as_judge(
        prompt=CORRECTNESS_PROMPT,
        model=JUDGE_MODEL,
        feedback_key="correctness",
    )
    return evaluator(
        inputs=inputs,
        outputs={"answer": outputs.get("answer")},
        reference_outputs={"answer": reference_outputs.get("answer")},
    )
