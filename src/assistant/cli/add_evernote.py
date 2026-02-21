"""CLI script to add an Evernote external source with a list of notebooks."""

import argparse
import json
import logging
import sys

from assistant.models.database import get_session_factory
from assistant.models.schema import ExternalSource

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    """Add an ExternalSource row for Evernote with the given notebooks.

    Creates a row in the external_sources table with provider "evernote" and
    provider_query set to a JSON object {"notebooks": [notebook names]}.

    Returns:
        0 on success, 1 on error.
    """
    parser = argparse.ArgumentParser(
        description="Add an Evernote external source with a list of notebooks",
    )
    parser.add_argument(
        "notebooks",
        nargs="+",
        metavar="NOTEBOOK",
        help="One or more notebook names to sync from Evernote",
    )
    args = parser.parse_args()

    if not args.notebooks:
        logger.error("At least one notebook is required")
        return 1

    config = {"notebooks": args.notebooks}
    provider_query = json.dumps(config)

    try:
        session_factory = get_session_factory()
        with session_factory() as session:
            source = ExternalSource(
                provider="evernote",
                provider_query=provider_query,
            )
            session.add(source)
            session.commit()
            logger.info(
                "Added Evernote source id=%s with notebooks: %s",
                source.id,
                args.notebooks,
            )
    except Exception:
        logger.exception("Failed to add Evernote source")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
