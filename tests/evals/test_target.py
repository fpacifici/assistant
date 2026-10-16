"""Tests for the evaluation target and evaluators (no real models)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from assistant.agents.rag import AskAgent
from assistant.evals import target as target_module
from assistant.evals.target import (
    EvalContext,
    ask,
    correctness_evaluator,
    eval_user_email,
)
from assistant.models.schema import ChatThread, User
from assistant.notes.service import create_note, create_notebook
from tests.agents.fakes import (
    FakeSearcher,
    MemoryCheckpointer,
    ScriptedChatModel,
    hit,
    tool_call,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager

    from sqlalchemy.orm import Session


@pytest.fixture
def eval_user(db_session: Session) -> User:
    user = User(email="eval@assistant.invalid", firstname="Eval", lastname="User")
    db_session.add(user)
    db_session.flush()
    return user


def _context(
    factory: Callable[[], AbstractContextManager[Session]],
    user: User,
    model: ScriptedChatModel,
    searcher: FakeSearcher,
) -> EvalContext:
    agent = AskAgent(
        factory,  # type: ignore[arg-type]
        searcher,  # type: ignore[arg-type]
        model,
        checkpointer=MemoryCheckpointer(),
    )
    return EvalContext(
        session_factory=factory,  # type: ignore[arg-type]
        agent=agent,
        user_id=user.uid,
    )


# --- Target ---


def test_ask_returns_answer_and_sources_then_cleans_up(
    db_session: Session,
    db_session_factory: Callable[[], AbstractContextManager[Session]],
    eval_user: User,
) -> None:
    notebook = create_notebook(db_session, "Travel", eval_user)
    note = create_note(db_session, notebook_id=notebook.id, owner=eval_user, title="Rome")
    model = ScriptedChatModel(
        script=[tool_call("search_notes", query="rome"), AIMessage(content="In May.")],
    )
    context = _context(
        db_session_factory, eval_user, model, FakeSearcher([hit(note.id, "Rome")])
    )

    outputs = ask(context, "When did I go to Rome?")

    assert outputs == {
        "answer": "In May.",
        "sources": ["Rome"],
        "notebooks": ["Travel"],
        "error": None,
    }
    assert db_session.query(ChatThread).count() == 0


def test_ask_reports_errors_as_the_answer(
    db_session_factory: Callable[[], AbstractContextManager[Session]],
    eval_user: User,
) -> None:
    model = ScriptedChatModel(script=[], error=RuntimeError("boom"))
    context = _context(db_session_factory, eval_user, model, FakeSearcher())

    outputs = ask(context, "Anything?")

    assert outputs["error"] == outputs["answer"]
    assert outputs["sources"] == []


def test_target_needs_ai() -> None:
    target_module._context.cache_clear()
    with (
        patch("assistant.evals.target.get_session_factory"),
        pytest.raises(RuntimeError, match="OPENAI_API_KEY"),
    ):
        target_module.target({"question": "Hi"})
    target_module._context.cache_clear()


def test_eval_user_email(monkeypatch: pytest.MonkeyPatch) -> None:
    assert eval_user_email() == "eval@assistant.invalid"
    monkeypatch.setenv("EVAL_USER_EMAIL", "someone@test.com")
    assert eval_user_email() == "someone@test.com"


# --- Evaluators ---


def test_correctness_evaluator_compares_answers() -> None:
    judge = MagicMock(return_value={"key": "correctness", "score": True})
    with patch("assistant.evals.target.create_llm_as_judge", return_value=judge):
        result = correctness_evaluator(
            inputs={"question": "q"},
            outputs={"answer": "a", "sources": ["x"]},
            reference_outputs={"answer": "b", "sources": ["y"]},
        )

    assert result == {"key": "correctness", "score": True}
    judge.assert_called_once_with(
        inputs={"question": "q"},
        outputs={"answer": "a"},
        reference_outputs={"answer": "b"},
    )
