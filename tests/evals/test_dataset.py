"""Tests for keeping the LangSmith dataset in sync with the YAML file."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest

from assistant.evals.dataset import SyncResult, load_examples, sync_dataset

if TYPE_CHECKING:
    from pathlib import Path

_YAML = """
- inputs: {question: "Where?"}
  outputs: {answer: Rome, sources: [Rome]}
- inputs: {question: "When?"}
  outputs: {answer: May, sources: []}
"""


@pytest.fixture
def dataset_file(tmp_path: Path) -> Path:
    path = tmp_path / "dataset.yaml"
    path.write_text(_YAML)
    return path


def _example(inputs: dict[str, Any], outputs: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), inputs=inputs, outputs=outputs)


# --- Loading ---


def test_load_examples(dataset_file: Path) -> None:
    examples = load_examples(dataset_file)

    assert [e["inputs"]["question"] for e in examples] == ["Where?", "When?"]


def test_load_examples_needs_a_list(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("question: where\n")

    with pytest.raises(ValueError, match="list of examples"):
        load_examples(path)


def test_load_examples_needs_questions(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("- outputs: {answer: Rome}\n")

    with pytest.raises(ValueError, match=r"no inputs\.question"):
        load_examples(path)


# --- Syncing ---


def test_creates_a_missing_dataset(dataset_file: Path) -> None:
    client = MagicMock()
    client.has_dataset.return_value = False

    assert sync_dataset(client, dataset_file, "DS") == SyncResult.CREATED

    client.create_dataset.assert_called_once()
    examples = client.create_examples.call_args.kwargs["examples"]
    assert len(examples) == 2


def test_leaves_an_identical_dataset_alone(dataset_file: Path) -> None:
    client = MagicMock()
    client.has_dataset.return_value = True
    client.list_examples.return_value = [
        _example({"question": "When?"}, {"answer": "May", "sources": []}),
        _example({"question": "Where?"}, {"answer": "Rome", "sources": ["Rome"]}),
    ]

    assert sync_dataset(client, dataset_file, "DS") == SyncResult.UNCHANGED

    client.delete_examples.assert_not_called()
    client.create_examples.assert_not_called()


def test_replaces_the_examples_of_a_changed_dataset(dataset_file: Path) -> None:
    client = MagicMock()
    client.has_dataset.return_value = True
    old = _example({"question": "Where?"}, {"answer": "Paris", "sources": []})
    client.list_examples.return_value = [old]

    assert sync_dataset(client, dataset_file, "DS") == SyncResult.UPDATED

    client.delete_examples.assert_called_once_with([old.id])
    assert len(client.create_examples.call_args.kwargs["examples"]) == 2
