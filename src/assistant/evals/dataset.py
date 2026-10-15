"""The LangSmith dataset of eval questions, kept in sync with a YAML file.

The YAML file (`data/evals/dataset.yaml`) is a list of examples:

    - inputs: {question: ...}
      outputs: {answer: ..., sources: [note titles]}

`sync_dataset` creates the dataset on first use and replaces its examples
whenever the file changed, so experiments always run on the questions in
the repository.
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import TYPE_CHECKING, Any, cast

from yaml import safe_load

if TYPE_CHECKING:
    from pathlib import Path

    from langsmith import Client

DATASET_NAME = "Assistant notes eval"
DATASET_DESCRIPTION = (
    "Questions about the eval corpus (data/evals/notes) for the Ask AI agent"
)


class SyncResult(StrEnum):
    """What `sync_dataset` did."""

    CREATED = "created"
    UPDATED = "updated"
    UNCHANGED = "unchanged"


def load_examples(path: Path) -> list[dict[str, Any]]:
    """Read and check the examples of a dataset YAML file.

    Raises:
        ValueError: If the file is not a list of examples with a question.
    """
    examples = safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(examples, list):
        msg = f"{path}: expected a list of examples"
        raise ValueError(msg)  # noqa: TRY004
    for index, example in enumerate(examples):
        if not isinstance(example, dict) or not isinstance(
            example.get("inputs", {}).get("question"),
            str,
        ):
            msg = f"{path}: example {index} has no inputs.question"
            raise ValueError(msg)  # noqa: TRY004
    return cast("list[dict[str, Any]]", examples)


def _fingerprint(examples: list[dict[str, Any]]) -> list[str]:
    return sorted(
        json.dumps(
            {"inputs": e.get("inputs"), "outputs": e.get("outputs")}, sort_keys=True
        )
        for e in examples
    )


def sync_dataset(client: Client, path: Path, name: str = DATASET_NAME) -> SyncResult:
    """Make the LangSmith dataset `name` hold exactly the examples in `path`."""
    examples = load_examples(path)
    if not client.has_dataset(dataset_name=name):
        dataset = client.create_dataset(name, description=DATASET_DESCRIPTION)
        client.create_examples(dataset_id=dataset.id, examples=examples)
        return SyncResult.CREATED

    dataset = client.read_dataset(dataset_name=name)
    existing = list(client.list_examples(dataset_id=dataset.id))
    current = [{"inputs": e.inputs, "outputs": e.outputs} for e in existing]
    if _fingerprint(current) == _fingerprint(examples):
        return SyncResult.UNCHANGED
    if existing:
        client.delete_examples([e.id for e in existing])
    client.create_examples(dataset_id=dataset.id, examples=examples)
    return SyncResult.UPDATED
