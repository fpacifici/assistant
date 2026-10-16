"""CLI to chat with the Ask AI agent in a terminal UI.

Usage:
    python -m assistant.cli.chat --email EMAIL [--thread-id UUID]

Without `--thread-id` a new thread is started (and listed in the web UI's
Ask AI page); its id is printed on exit so the conversation can be resumed.
"""

from __future__ import annotations

import argparse
import logging
import sys
import uuid

from assistant.agents.rag import create_ask_agent
from assistant.agents.tracing import configure_tracing
from assistant.chat.service import create_thread, get_thread, record_question
from assistant.models.database import get_session_factory
from assistant.notes.user_service import get_user, get_user_by_email
from assistant.tui.app import ChatApp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Chat with the Ask AI agent about a user's notes",
    )
    parser.add_argument("--email", required=True, help="The user asking")
    parser.add_argument(
        "--thread-id",
        type=uuid.UUID,
        help="Resume this thread of the user (default: start a new one)",
    )
    return parser.parse_args()


def main() -> int:
    """Start the chat TUI.

    Returns:
        0 on normal exit, 1 on error.
    """
    args = _parse_args()
    try:
        configure_tracing()
        session_factory = get_session_factory()
        agent = create_ask_agent(session_factory)
        if agent is None:
            logger.error("AI is disabled: set OPENAI_API_KEY")
            return 1
        with session_factory() as session:
            user = get_user_by_email(session, args.email)
            if args.thread_id is None:
                thread = create_thread(session, user)
            else:
                thread = get_thread(session, user, args.thread_id)
            session.commit()
            user_id, thread_id = user.uid, thread.id

        def on_question(question: str) -> None:
            with session_factory() as session:
                record_question(session, get_user(session, user_id), thread_id, question)
                session.commit()

        app = ChatApp(thread_id, user_id, agent, on_question=on_question)
        app.run(mouse=False)  # allow terminal to handle mouse for text selection/copy
    except Exception:
        logger.exception("Chat TUI failed")
        return 1
    print(f"Thread id: {thread_id}")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
