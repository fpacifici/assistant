"""Analyze every reading link still waiting for analysis.

The API analyzes links as they are saved, when AI is enabled. This picks up
what it left: links saved while AI was off, or pending when the server
stopped. Each link is tried until it is analyzed or has failed for the last
time. It exits with 1 if any link failed.

Usage:
    python -m assistant.cli.process_reading [--user-id UID] [--link-id ID]
"""

from __future__ import annotations

import argparse
import logging
import sys
import uuid
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from assistant.agents.tracing import configure_tracing
from assistant.config import Config
from assistant.models.database import get_engine
from assistant.models.schema import ReadingAnalysisStatus, ReadingLink
from assistant.observability import init_sentry
from assistant.reading.analysis import (
    MAX_ATTEMPTS,
    LinkAnalyzer,
    LinkProcessor,
    Outcome,
    create_link_analyzer,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--user-id", type=uuid.UUID, help="Only this user's links")
    parser.add_argument("--link-id", type=uuid.UUID, help="Only this link")
    return parser.parse_args(argv)


def pending_link_ids(
    session: Session,
    *,
    user_id: uuid.UUID | None = None,
    link_id: uuid.UUID | None = None,
) -> list[uuid.UUID]:
    """The links waiting for analysis, oldest first."""
    stmt = select(ReadingLink.id).where(
        ReadingLink.analysis_status == ReadingAnalysisStatus.PENDING
    )
    if user_id is not None:
        stmt = stmt.where(ReadingLink.owner_id == user_id)
    if link_id is not None:
        stmt = stmt.where(ReadingLink.id == link_id)
    return list(session.scalars(stmt.order_by(ReadingLink.created_at, ReadingLink.id)))


def process_pending(
    session_factory: sessionmaker[Session],
    analyzer: LinkAnalyzer,
    *,
    user_id: uuid.UUID | None = None,
    link_id: uuid.UUID | None = None,
) -> Counter[Outcome]:
    """Analyze the pending links, each until it is no longer pending.

    Returns:
        How many links ended with each outcome.
    """
    processor = LinkProcessor(session_factory, analyzer)
    with session_factory() as session:
        link_ids = pending_link_ids(session, user_id=user_id, link_id=link_id)
    outcomes: Counter[Outcome] = Counter()
    for pending_id in link_ids:
        outcome = processor.process(pending_id)
        for _ in range(MAX_ATTEMPTS - 1):
            if outcome is not Outcome.RETRY:
                break
            outcome = processor.process(pending_id)
        outcomes[outcome] += 1
    return outcomes


def main(argv: list[str] | None = None) -> int:
    """Run the analysis.

    Returns:
        0 on success, 1 if AI is disabled or any link failed.
    """
    args = _parse_args(argv)
    config = Config()
    init_sentry(config)
    configure_tracing(config)
    analyzer = create_link_analyzer(config)
    if analyzer is None:
        logger.error("AI is disabled: set OPENAI_API_KEY to analyze reading links")
        return 1
    session_factory = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)
    outcomes = process_pending(
        session_factory, analyzer, user_id=args.user_id, link_id=args.link_id
    )
    logger.info(
        "Analyzed %d links: %d summarized, %d not summarizable, %d failed, "
        "%d still pending, %d skipped",
        sum(outcomes.values()),
        outcomes[Outcome.DONE],
        outcomes[Outcome.NOT_SUMMARIZABLE],
        outcomes[Outcome.FAILED],
        outcomes[Outcome.RETRY],
        outcomes[Outcome.SKIPPED],
    )
    return 1 if outcomes[Outcome.FAILED] or outcomes[Outcome.RETRY] else 0


if __name__ == "__main__":
    sys.exit(main())
