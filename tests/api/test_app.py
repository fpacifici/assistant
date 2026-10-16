"""Tests for the application factory."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from assistant.api.app import create_app

# --- Vector index worker ---


def test_worker_runs_for_the_lifetime_of_the_app() -> None:
    worker = MagicMock()
    app = create_app(session_factory=MagicMock(), vector_worker=worker)

    with TestClient(app):
        worker.start.assert_called_once_with()
        worker.stop.assert_not_called()

    worker.stop.assert_called_once_with()


def test_no_worker_when_ai_is_disabled() -> None:
    app = create_app(session_factory=MagicMock())

    assert app.state.vector_worker is None


def test_worker_built_from_config_when_ai_is_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    with patch("langchain_openai.OpenAIEmbeddings"):
        app = create_app(session_factory=MagicMock())

    assert app.state.vector_worker is not None
