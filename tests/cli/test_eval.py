"""Tests for evaluation CLI helpers."""

from __future__ import annotations

import pytest

from assistant.cli.eval import run_langsmith_evaluate


def test_run_langsmith_evaluate_calls_langsmith(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test that `run_langsmith_evaluate` calls `Client.evaluate` with expected args."""

    captured: dict[str, object] = {}

    class FakeClient:
        def evaluate(
            self,
            target: object,
            data: object,
            evaluators: list[object],
            experiment_prefix: str,
            max_concurrency: int,
        ) -> object:
            captured["data"] = data
            captured["evaluators"] = evaluators
            captured["experiment_prefix"] = experiment_prefix
            captured["max_concurrency"] = max_concurrency
            return {"experiment_prefix": experiment_prefix, "max_concurrency": max_concurrency}

    monkeypatch.setattr("assistant.cli.eval.Client", lambda: FakeClient())

    result = run_langsmith_evaluate(
        data="Sample dataset",
        experiment_prefix="first-eval-in-langsmith",
        max_concurrency=2,
    )

    assert isinstance(result, dict)
    assert captured["data"] == "Sample dataset"
    assert captured["experiment_prefix"] == "first-eval-in-langsmith"
    assert captured["max_concurrency"] == 2
    assert "correctness" in str(captured["evaluators"][0])

    out = capsys.readouterr().out
    assert "first-eval-in-langsmith" in out

