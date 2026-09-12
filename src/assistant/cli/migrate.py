"""CLI to apply or revert Alembic database migrations."""

import argparse
import logging
import sys

from assistant.models.database import downgrade_database, upgrade_database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    """Apply or revert Alembic migrations.

    Returns:
        0 on success, 1 on error.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    upgrade = sub.add_parser("upgrade", help="Apply pending migrations.")
    upgrade.add_argument(
        "revision",
        nargs="?",
        default="head",
        help="Target revision (default: head, i.e. every pending migration).",
    )

    downgrade = sub.add_parser("downgrade", help="Revert migrations.")
    downgrade.add_argument(
        "revision",
        nargs="?",
        default="-1",
        help="Target revision or relative step count (default: -1, one step back).",
    )

    args = parser.parse_args()

    try:
        if args.command == "upgrade":
            logger.info("Applying migrations to %s...", args.revision)
            upgrade_database(args.revision)
        else:
            logger.info("Reverting migrations to %s...", args.revision)
            downgrade_database(args.revision)
    except Exception:
        logger.exception("Migration command failed")
        return 1
    else:
        logger.info("Done")
        return 0


if __name__ == "__main__":
    sys.exit(main())
