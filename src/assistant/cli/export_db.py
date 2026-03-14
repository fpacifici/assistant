"""CLI script to export database and document contents."""

import argparse
import logging
import sys
from pathlib import Path

from assistant.config import Config
from assistant.export import run_export

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    """Export database and documents to a tar.gz archive.

    Returns:
        0 on success, 1 on error.
    """

    parser = argparse.ArgumentParser(
        description="Export assistant database and documents to a tar.gz archive",
    )
    parser.add_argument(
        "output",
        type=str,
        help="Path to the output .tar.gz archive",
    )
    parser.add_argument(
        "--config",
        type=str,
        help="Path to configuration file (default: config.yaml in project root)",
    )

    args = parser.parse_args()

    try:
        config = Config(config_path=args.config) if args.config else Config()
        output_path = Path(args.output)
        logger.info("Exporting database and documents to %s", output_path)
        run_export(config, output_path)
        logger.info("Export completed successfully")
    except Exception:
        logger.exception("Export failed")
        return 1
    else:
        return 0


if __name__ == "__main__":
    sys.exit(main())
