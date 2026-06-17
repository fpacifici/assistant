"""CLI script for evaluation-related actions."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, cast

from langsmith import Client

from assistant.agents.infra import init_environment
from assistant.evals.dataset import create_dataset
from assistant.evals.target import correctness_evaluator, target as langsmith_target

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def run_langsmith_evaluate() -> object:
    """Run LangSmith evaluation with OpenEvals evaluators.

    Args:
        data: Dataset name or dataset-like object accepted by `Client.evaluate`.
        experiment_prefix: Prefix used for the LangSmith experiment naming.
        max_concurrency: Maximum number of concurrent evaluations.

    Returns:
        The result object returned by LangSmith.
    """

    client = cast(Any, Client())
    experiment_results = client.evaluate(
        langsmith_target,
        data="Assistant dataset",
        evaluators=[correctness_evaluator],
        experiment_prefix="first-eval-in-langsmith",
        max_concurrency=2,
    )
    print(experiment_results)
    return experiment_results


def main() -> int:
    """Run evaluation actions from the command line.

    Returns:
        Exit code. `0` on success, `1` on failure.
    """
    parser = argparse.ArgumentParser(
        description="Run evaluation actions.",
    )
    parser.add_argument(
        "action",
        choices=["createdataset", "langsmith-evaluate"],
        help="Evaluation action to run.",
    )
    parser.add_argument("yaml_file", nargs="?", type=Path, help="Path to the YAML file.")
    parser.add_argument("--data", type=str, default="Sample dataset", help="Dataset name for evaluation.")
    parser.add_argument(
        "--experiment-prefix",
        type=str,
        default="first-eval-in-langsmith",
        help="LangSmith experiment prefix.",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=2,
        help="Maximum concurrent evaluation jobs.",
    )
    args = parser.parse_args()

    if args.action == "createdataset":
        if args.yaml_file is None:
            logger.error("yaml_file is required for createdataset")
            return 1
        if not args.yaml_file.exists():
            logger.error("YAML file does not exist: %s", args.yaml_file)
            return 1
        if not args.yaml_file.is_file():
            logger.error("Path is not a file: %s", args.yaml_file)
            return 1

        try:
            init_environment()
            create_dataset(args.yaml_file)
            logger.info("Dataset created from %s", args.yaml_file)
        except Exception:
            logger.exception("Failed to create dataset")
            return 1

        return 0
    if args.action == "langsmith-evaluate":
        try:
            init_environment()
            run_langsmith_evaluate()
        except Exception:
            logger.exception("LangSmith evaluation failed")
            return 1
        return 0

    logger.error("Unsupported action: %s", args.action)
    return 1


if __name__ == "__main__":
    sys.exit(main())
