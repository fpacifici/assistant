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
from assistant.evals.target import correctness_evaluator
from assistant.evals.target import target as langsmith_target

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def run_langsmith_evaluate(
    *,
    data: str,
    experiment_prefix: str,
    max_concurrency: int,
) -> object:
    """Run LangSmith evaluation with OpenEvals evaluators.

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
        evaluators=[correctness_evaluator],
        experiment_prefix=experiment_prefix,
        max_concurrency=max_concurrency,
    )
    print(experiment_results)  # noqa: T201
    return experiment_results


def _create_dataset(yaml_file: Path | None) -> int:
    """Create a LangSmith dataset from a YAML file.

    Args:
        yaml_file: Path to the dataset YAML file.

    Returns:
        Exit code. `0` on success, `1` on failure.
    """
    if yaml_file is None:
        logger.error("yaml_file is required for createdataset")
        return 1
    if not yaml_file.is_file():
        logger.error("YAML file does not exist or is not a file: %s", yaml_file)
        return 1

    try:
        init_environment()
        create_dataset(yaml_file)
        logger.info("Dataset created from %s", yaml_file)
    except Exception:
        logger.exception("Failed to create dataset")
        return 1
    return 0


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
    parser.add_argument(
        "--data",
        type=str,
        default="Assistant dataset",
        help="Dataset name for evaluation.",
    )
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
        return _create_dataset(args.yaml_file)
    if args.action == "langsmith-evaluate":
        try:
            init_environment()
            run_langsmith_evaluate(
                data=args.data,
                experiment_prefix=args.experiment_prefix,
                max_concurrency=args.max_concurrency,
            )
        except Exception:
            logger.exception("LangSmith evaluation failed")
            return 1
        return 0

    logger.error("Unsupported action: %s", args.action)
    return 1


if __name__ == "__main__":
    sys.exit(main())
