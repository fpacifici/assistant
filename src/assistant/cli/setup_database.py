"""Script to set up the database schema."""

import logging
import sys

from assistant.models.database import init_database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    """Initialize the database schema.

    Returns:
        0 on success, 1 on error.
    """
    try:
        logger.info("Initializing database schema...")
        init_database()
        logger.info("Database schema initialized successfully")
    except Exception:
        logger.exception("Failed to initialize database schema")
        return 1
    else:
        return 0


if __name__ == "__main__":
    sys.exit(main())
