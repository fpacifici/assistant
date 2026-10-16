"""CLI to ask the Ask AI agent one question and print the streamed answer.

Usage:
    python -m assistant.cli.query --email EMAIL "What did I plan for Rome?"

The question is asked in a new thread of the user, so it also shows up in
the web UI's Ask AI page. Tool calls and sources go to stderr, the answer
to stdout.
"""

from __future__ import annotations

import argparse
import logging
import sys

from assistant.agents.rag import (
    ErrorEvent,
    SourcesEvent,
    TokenEvent,
    ToolEvent,
    create_ask_agent,
)
from assistant.agents.tracing import configure_tracing
from assistant.chat.service import create_thread, record_question
from assistant.models.database import get_session_factory
from assistant.notes.user_service import get_user_by_email

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    """Ask one question and print the answer.

    Returns:
        0 on success, 1 on error.
    """
    parser = argparse.ArgumentParser(description="Ask the Ask AI agent one question")
    parser.add_argument("--email", required=True, help="The user asking")
    parser.add_argument("question", type=str, help="The question")
    args = parser.parse_args()

    try:
        configure_tracing()
        session_factory = get_session_factory()
        agent = create_ask_agent(session_factory)
        if agent is None:
            logger.error("AI is disabled: set OPENAI_API_KEY")
            return 1
        with session_factory() as session:
            user = get_user_by_email(session, args.email)
            thread = create_thread(session, user)
            record_question(session, user, thread.id, args.question)
            session.commit()
            user_id, thread_id = user.uid, thread.id

        failed = False
        for event in agent.stream(thread_id, user_id, args.question):
            if isinstance(event, TokenEvent):
                sys.stdout.write(event.text)
                sys.stdout.flush()
            elif isinstance(event, ToolEvent) and event.status == "start":
                sys.stderr.write(f"→ {event.name}({event.input})\n")
            elif isinstance(event, SourcesEvent):
                sys.stdout.write("\n")
                for source in event.sources:
                    sys.stderr.write(f"Source: {source['title']} ({source['note_id']})\n")
            elif isinstance(event, ErrorEvent):
                sys.stderr.write(f"Error: {event.message}\n")
                failed = True
    except Exception:
        logger.exception("Query failed")
        return 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
