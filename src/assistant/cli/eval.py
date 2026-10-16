"""CLI to run the Ask AI evals against LangSmith.

Usage:
    python -m assistant.cli.eval load-corpus [--corpus DIR]
    python -m assistant.cli.eval sync-dataset [--dataset-file FILE]
    python -m assistant.cli.eval evaluate [--experiment-prefix P] [--max-concurrency N]

`make eval` runs all three. The evals call OpenAI and LangSmith with real
keys (`OPENAI_API_KEY`, `LANGSMITH_API_KEY`), so they are run by hand and
refuse to run in CI (when `CI` is set).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any, cast

from langsmith import Client

from assistant.agents.tracing import configure_tracing
from assistant.evals.corpus import load_corpus
from assistant.evals.dataset import DATASET_NAME, sync_dataset
from assistant.evals.target import (
    correctness_evaluator,
    eval_user_email,
    retrieval_evaluator,
)
from assistant.evals.target import target as langsmith_target
from assistant.models.database import get_session_factory
from assistant.vectors.indexer import create_vector_indexer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CORPUS = _REPO_ROOT / "data" / "evals" / "notes"
DEFAULT_DATASET_FILE = _REPO_ROOT / "data" / "evals" / "dataset.yaml"


def run_load_corpus(corpus: Path) -> int:
    """Load the corpus into the eval user's notebooks and embed it.

    Returns:
        Exit code.
    """
    indexer = create_vector_indexer()
    if indexer is None:
        logger.error("AI is disabled: set OPENAI_API_KEY to embed the corpus")
        return 1
    session_factory = get_session_factory()
    with session_factory() as session:
        notes = load_corpus(session, corpus, eval_user_email())
        session.commit()
        note_ids = [note.id for note in notes]
    for note_id in note_ids:
        with session_factory() as session:
            indexer.index_note(session, note_id)
            session.commit()
    logger.info("Loaded and embedded %d notes for %s", len(note_ids), eval_user_email())
    return 0


def run_sync_dataset(dataset_file: Path, name: str) -> int:
    """Create or update the LangSmith dataset from the YAML file.

    Returns:
        Exit code.
    """
    result = sync_dataset(Client(), dataset_file, name)
    logger.info("Dataset %r %s from %s", name, result, dataset_file)
    return 0


def run_langsmith_evaluate(
    *,
    data: str,
    experiment_prefix: str,
    max_concurrency: int,
) -> object:
    """Run LangSmith evaluation with the Ask AI evaluators.

    Args:
        data: Dataset name or dataset-like object accepted by `Client.evaluate`.
        experiment_prefix: Prefix used for the LangSmith experiment naming.
        max_concurrency: Maximum number of concurrent evaluations.

    Returns:
        The result object returned by LangSmith.
    """

    client = cast("Any", Client())
    experiment_results = client.evaluate(
        langsmith_target,
        data=data,
        evaluators=[correctness_evaluator, retrieval_evaluator],
        experiment_prefix=experiment_prefix,
        max_concurrency=max_concurrency,
    )
    print(experiment_results)  # noqa: T201
    return experiment_results


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Ask AI evals.")
    parser.add_argument(
        "action",
        choices=["load-corpus", "sync-dataset", "evaluate"],
        help="Evaluation action to run.",
    )
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--dataset-file", type=Path, default=DEFAULT_DATASET_FILE)
    parser.add_argument("--data", type=str, default=DATASET_NAME, help="Dataset name.")
    parser.add_argument("--experiment-prefix", type=str, default="ask-ai")
    parser.add_argument("--max-concurrency", type=int, default=2)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run evaluation actions from the command line.

    Returns:
        Exit code. `0` on success, `1` on failure.
    """
    args = _parse_args(argv)
    if os.getenv("CI"):
        logger.error("The evals call paid APIs with real keys: they never run in CI")
        return 1
    configure_tracing()
    try:
        if args.action == "load-corpus":
            return run_load_corpus(args.corpus)
        if args.action == "sync-dataset":
            return run_sync_dataset(args.dataset_file, args.data)
        run_langsmith_evaluate(
            data=args.data,
            experiment_prefix=args.experiment_prefix,
            max_concurrency=args.max_concurrency,
        )
    except Exception:
        logger.exception("Eval action %s failed", args.action)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
