"""Tests for the eval CLI (no real models or LangSmith)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from assistant.cli.eval import main, run_langsmith_evaluate
from assistant.evals.dataset import SyncResult
from assistant.models.schema import Note
from assistant.vectors.indexer import IndexOutcome

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager
    from pathlib import Path

    from sqlalchemy.orm import Session


@pytest.fixture(autouse=True)
def _not_in_ci(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CI", raising=False)


# --- CI guard ---


def test_refuses_to_run_in_ci(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CI", "true")

    with patch("assistant.cli.eval.run_langsmith_evaluate") as evaluate:
        assert main(["evaluate"]) == 1

    evaluate.assert_not_called()


# --- evaluate ---


def test_run_langsmith_evaluate_calls_langsmith(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = MagicMock()
    client.evaluate.return_value = "results"
    monkeypatch.setattr("assistant.cli.eval.Client", lambda: client)

    result = run_langsmith_evaluate(
        data="Sample dataset",
        experiment_prefix="ask-ai",
        max_concurrency=2,
    )

    assert result == "results"
    kwargs = client.evaluate.call_args.kwargs
    assert kwargs["data"] == "Sample dataset"
    assert kwargs["experiment_prefix"] == "ask-ai"
    assert kwargs["max_concurrency"] == 2
    assert [e.__name__ for e in kwargs["evaluators"]] == [
        "correctness_evaluator",
        "retrieval_evaluator",
    ]
    assert "results" in capsys.readouterr().out


def test_evaluate_failure_is_an_exit_code() -> None:
    with patch("assistant.cli.eval.run_langsmith_evaluate", side_effect=RuntimeError):
        assert main(["evaluate"]) == 1


# --- sync-dataset ---


def test_sync_dataset(tmp_path: Path) -> None:
    dataset_file = tmp_path / "dataset.yaml"
    with (
        patch("assistant.cli.eval.Client") as client_cls,
        patch("assistant.cli.eval.sync_dataset", return_value=SyncResult.CREATED) as sync,
    ):
        assert (
            main(["sync-dataset", "--dataset-file", str(dataset_file), "--data", "DS"])
            == 0
        )

    sync.assert_called_once_with(client_cls.return_value, dataset_file, "DS")


# --- load-corpus ---


def test_load_corpus_needs_ai() -> None:
    assert main(["load-corpus"]) == 1


def test_load_corpus_loads_and_embeds(
    db_session: Session,
    db_session_factory: Callable[[], AbstractContextManager[Session]],
    tmp_path: Path,
) -> None:
    (tmp_path / "Travel").mkdir()
    (tmp_path / "Travel" / "rome.md").write_text("# Rome\n\nColosseum.\n")
    indexer = MagicMock()
    indexer.index_note.return_value = IndexOutcome.EMBEDDED
    with (
        patch("assistant.cli.eval.create_vector_indexer", return_value=indexer),
        patch("assistant.cli.eval.get_session_factory", return_value=db_session_factory),
    ):
        assert main(["load-corpus", "--corpus", str(tmp_path)]) == 0

    [note] = db_session.query(Note).all()
    assert note.title == "Rome"
    indexer.index_note.assert_called_once_with(db_session, note.id)
