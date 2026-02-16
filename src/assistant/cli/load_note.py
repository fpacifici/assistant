"""CLI script to load a note by notebook name."""

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from typing import cast

from assistant.adapters.evernote import EvernoteSource
from assistant.cli.table import print_table
from evernote_backup.cli_app_auth import get_auth_token, get_sync_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _parse_iso_datetime(value: str) -> datetime:
    """Parse an ISO 8601 datetime string (e.g. 2021-01-15 or 2021-01-15T12:00:00+00:00)."""
    s = value.strip().replace("Z", "+00:00")
    return datetime.fromisoformat(s)


def main() -> int:
    """Main entry point for the load_note CLI script.

    Returns:
        0 on success, 1 on error.
    """
    parser = argparse.ArgumentParser(
        description="Load a note by notebook name",
    )
    parser.add_argument(
        "notebook_name",
        type=str,
        help="Name of the notebook",
    )
    parser.add_argument(
        "--since",
        type=_parse_iso_datetime,
        default=None,
        metavar="DATETIME",
        help="Only list notes updated since this datetime (ISO format). Default: 1 day ago.",
    )

    args = parser.parse_args()

    notebook_name = args.notebook_name
    since = args.since if args.since is not None else datetime.now(timezone.utc) - timedelta(days=1)

    evernote = EvernoteSource(notebooks=["dist/stream"])
    notes = evernote.list_documents(since=since)
    for note in notes:
        print(evernote.get_document(note))

    return 0
    

if __name__ == "__main__":
    sys.exit(main())
