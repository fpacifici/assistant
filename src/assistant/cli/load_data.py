"""CLI script to trigger the DataLoad job."""

import argparse
import logging
import sys

from assistant.adapters.dataload import load_data
from assistant.agents.infra import init_environment
from assistant.config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _register_plugins() -> None:
    """Register available plugins.

    The registry now hardcodes provider classes at construction time, so this function is retained
    for backward compatibility (e.g. CLI/tests) and is intentionally a no-op.
    """


def main() -> int:
    """Main entry point for the load_data CLI script.

    Returns:
        0 on success, 1 on error.
    """
    parser = argparse.ArgumentParser(
        description="Load data from external sources into the database",
    )
    parser.add_argument(
        "--config",
        type=str,
        help="Path to configuration file (default: config.yaml in project root)",
    )

    args = parser.parse_args()

    try:
        # Load configuration
        config = Config(config_path=args.config) if args.config else Config()

        _register_plugins()

        # Run data load
        logger.info("Starting data load job...")
        init_environment()
        load_data(config)
        logger.info("Data load job completed successfully")
    except Exception:
        logger.exception("Data load job failed")
        return 1
    else:
        return 0


if __name__ == "__main__":
    sys.exit(main())
