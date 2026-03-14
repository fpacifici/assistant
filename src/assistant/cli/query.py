"""CLI script to run a semantic query against the VectorStore and print results."""

import argparse
import logging
import sys

from assistant.agents.infra import init_environment
from assistant.agents.rag import SearchAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    """Run a query on the VectorStore and print matching documents with scores.

    Returns:
        0 on success, 1 on error.
    """
    parser = argparse.ArgumentParser(
        description="Query the VectorStore and print similar documents",
    )
    parser.add_argument(
        "query",
        type=str,
        help="The search query string",
    )
    parser.add_argument(
        "--thread-id",
        "-t",
        type=str,
        help="The thread ID",
    )
    args = parser.parse_args()
    thread_id = args.thread_id
    try:
        init_environment()
        store = SearchAgent()
        messages = []
        logger.info("Thread ID: %s", thread_id)
        for event in store.query(thread_id, args.query):
            event.pretty_print()
            messages.append(event)
    except Exception:
        logger.exception("Query failed")
        return 1
    else:
        return 0


if __name__ == "__main__":
    sys.exit(main())
