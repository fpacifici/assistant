"""CLI script to import database and document contents from an archive."""

import argparse
import logging
import sys
from pathlib import Path

from assistant.config import Config
from assistant.restore import run_restore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    """Import database and documents from a tar.gz archive.

    Returns:
        0 on success, 1 on error.
    """

    parser = argparse.ArgumentParser(
        description="Import assistant database and documents from a tar.gz archive",
    )
    parser.add_argument(
        "archive",
        type=str,
        help="Path to the input .tar.gz archive produced by the export command",
    )
    parser.add_argument(
        "--config",
        type=str,
        help="Path to configuration file (default: config.yaml in project root)",
    )

    args = parser.parse_args()

    try:
        config = Config(config_path=args.config) if args.config else Config()
        archive_path = Path(args.archive)
        logger.info("Importing database and documents from %s", archive_path)
        run_restore(config, archive_path)
        logger.info("Import completed successfully")
        return 0
    except Exception:  # noqa: BLE001
        logger.exception("Import failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())

