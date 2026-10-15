"""Tests for LangSmith tracing configuration."""

from __future__ import annotations

import os

import pytest

from assistant.agents.tracing import configure_tracing


@pytest.fixture(autouse=True)
def _restore_langsmith_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let monkeypatch restore the variables configure_tracing writes."""
    for key in ("LANGSMITH_TRACING", "LANGSMITH_PROJECT", "LANGSMITH_ENDPOINT"):
        monkeypatch.setenv(key, "")
        monkeypatch.delenv(key)


def test_tracing_off_without_api_key() -> None:
    assert configure_tracing() is False
    assert os.environ["LANGSMITH_TRACING"] == "false"


def test_tracing_on_with_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2-test")

    assert configure_tracing() is True
    assert os.environ["LANGSMITH_TRACING"] == "true"
    assert os.environ["LANGSMITH_PROJECT"] == "Assistant"
    assert os.environ["LANGSMITH_ENDPOINT"] == "https://api.smith.langchain.com"


def test_tracing_project_from_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2-test")
    monkeypatch.setenv("AI_LANGSMITH_PROJECT", "Assistant-dev")

    configure_tracing()

    assert os.environ["LANGSMITH_PROJECT"] == "Assistant-dev"
