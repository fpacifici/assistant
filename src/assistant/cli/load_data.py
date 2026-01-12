"""CLI script to trigger the DataLoad job."""

import argparse
import logging
import sys

from assistant.adapters.dataload import load_data
from assistant.adapters.plugins.fake import FakeExternalSource
from assistant.adapters.registry import get_registry
from assistant.config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _register_plugins() -> None:
    """Register all available plugins with the registry."""
    registry = get_registry()
    registry.register("fake", FakeExternalSource)
    logger.debug("Registered plugins")


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

        # Register plugins
        _register_plugins()

        # Run data load
        logger.info("Starting data load job...")
        load_data(config)
        logger.info("Data load job completed successfully")
    except Exception:
        logger.exception("Data load job failed")
        return 1
    else:
        return 0


if __name__ == "__main__":
    sys.exit(main())
