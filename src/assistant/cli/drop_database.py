"""Script to drop the assistant database schema and tables."""

import logging
import sys

from assistant.models.database import drop_database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    """Drop the assistant schema and all tables.

    Use before running setup_database when you need a clean state (e.g.
    between development attempts). With PostgreSQL, drops the 'assistant'
    schema. With SQLite, drops all assistant tables.

    Returns:
        0 on success, 1 on error.
    """
    try:
        logger.info("Dropping assistant schema and tables...")
        drop_database()
        logger.info("Database dropped successfully")
    except Exception:
        logger.exception("Failed to drop database")
        return 1
    else:
        return 0


if __name__ == "__main__":
    sys.exit(main())
