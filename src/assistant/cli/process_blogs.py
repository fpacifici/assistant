"""Collect new blog posts and summarize them.

Run this from cron; the system does not schedule it. It exits with 1 if
anything failed, and with 0 at once if another run holds the lock.

Usage:
    python -m assistant.cli.process_blogs [--user-id UID] [--source-id ID]
        [--dry-run]
"""

from __future__ import annotations

import argparse
import logging
import sys
import uuid

from sqlalchemy.orm import sessionmaker

from assistant.agents.tracing import configure_tracing
from assistant.blogs.analysis import create_post_analyzer
from assistant.blogs.pipeline import BlogPipeline, advisory_lock
from assistant.blogs.text_store import create_text_store
from assistant.config import Config
from assistant.models.database import get_engine
from assistant.observability import init_sentry
from assistant.vectors.indexer import create_vector_indexer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--user-id", type=uuid.UUID, help="Only this user's sources")
    parser.add_argument("--source-id", type=uuid.UUID, help="Only this source")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch sources and print what would be collected, without writing "
        "anything or calling a model",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the job.

    Returns:
        0 on success or if another run is active, 1 if anything failed.
    """
    args = _parse_args(argv)
    config = Config()
    init_sentry(config)
    configure_tracing(config)
    analyzer = None if args.dry_run else create_post_analyzer(config)
    if analyzer is None and not args.dry_run:
        logger.error("AI is disabled: set OPENAI_API_KEY to process blogs")
        return 1

    indexer = None if args.dry_run else create_vector_indexer(config)

    engine = get_engine()
    pipeline = BlogPipeline(
        sessionmaker(bind=engine, autoflush=False, autocommit=False),
        analyzer,
        indexer.embeddings if indexer else None,
        create_text_store(config),
        max_posts_per_run=config.get_blogs_config()["max_posts_per_run"],
    )
    with advisory_lock(engine) as acquired:
        if not acquired:
            logger.info("Another run is active, nothing to do")
            return 0
        report = pipeline.run(
            user_id=args.user_id, source_id=args.source_id, dry_run=args.dry_run
        )
    for source_title, url in report.would_collect:
        print(f"{source_title}: {url}")  # noqa: T201
    logger.info(
        "Checked %d sources: %d posts collected, %d analyzed, %d too short, "
        "%d embedded, %d text files swept, %d failures",
        report.sources_checked,
        report.posts_collected,
        report.posts_analyzed,
        report.posts_too_short,
        report.posts_embedded,
        report.files_swept,
        report.failures,
    )
    return 1 if report.failures else 0


if __name__ == "__main__":
    sys.exit(main())
