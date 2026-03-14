"""CLI to start the chat TUI for the RAG agent."""

import argparse
import logging
import sys

from assistant.agents.infra import init_environment
from assistant.agents.rag import SearchAgent
from assistant.tui.app import ChatApp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    """Start the chat TUI with the given thread ID.

    Returns:
        0 on normal exit, 1 on error.
    """
    parser = argparse.ArgumentParser(
        description="Start the chat TUI to send queries to the RAG agent",
    )
    parser.add_argument(
        "thread_id",
        type=str,
        help="Conversation thread ID",
    )
    args = parser.parse_args()
    try:
        init_environment()
        agent = SearchAgent()
        app = ChatApp(thread_id=args.thread_id, agent=agent)
        app.run(mouse=False)  # allow terminal to handle mouse for text selection/copy
    except Exception:
        logger.exception("Chat TUI failed")
        return 1
    else:
        return 0


if __name__ == "__main__":
    sys.exit(main())
