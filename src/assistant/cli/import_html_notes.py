"""CLI script to import a directory tree of exported HTML notes as real Notes."""

from __future__ import annotations

import argparse
import getpass
import logging
import os
import sys
from pathlib import Path

from assistant.adapters.notes_import import ImportReport, run_import
from assistant.adapters.plugins.html_file import HTMLFileImportSource
from assistant.auth.service import AuthError, authenticate_user
from assistant.models.database import get_session_factory

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _resolve_password(cli_password: str | None) -> str:
    """Resolve the import password from exactly one of arg / env var / prompt."""
    env_password = os.environ.get("NOTES_IMPORT_PASSWORD")
    if cli_password is not None and env_password is not None:
        msg = (
            "Password supplied via both --password and NOTES_IMPORT_PASSWORD;"
            " supply exactly one."
        )
        raise ValueError(msg)
    if cli_password is not None:
        return cli_password
    if env_password is not None:
        return env_password
    return getpass.getpass("Password: ")


def _log_report(report: ImportReport) -> None:
    """Log the counts, then one line per note or notebook that needs review."""
    logger.info(
        "Import complete: %d created, %d refreshed, %d unchanged,"
        " %d web clips skipped, %d web clips imported, %d notebooks",
        report.created,
        report.refreshed,
        report.unchanged,
        report.skipped_web_clip,
        report.imported_web_clip,
        report.notebooks_touched,
    )
    for kept in report.kept_modified:
        logger.warning(
            "Kept (edited after import on %s, last edit %s): %s",
            kept.imported_at,
            kept.modified_at,
            kept.source_path,
        )
    for kept in report.kept_untracked:
        logger.warning("Kept (imported before tracking): %s", kept.source_path)
    for duplicate in report.duplicate_title:
        logger.warning(
            "Not imported (duplicate title %r): %s",
            duplicate.title,
            duplicate.source_path,
        )
    for failed_notebook in report.notebooks_failed:
        logger.error(
            "Notebook skipped (%s, %d notes): %s",
            failed_notebook.reason,
            failed_notebook.skipped_notes,
            failed_notebook.name,
        )
    for failed in report.failed:
        logger.error("Failed (%s): %s", failed.error, failed.source_path)


def main() -> int:
    """Import a directory tree of exported HTML notes as real Notes.

    Returns:
        0 on success, 1 on error.
    """
    parser = argparse.ArgumentParser(
        description="Import a directory tree of exported HTML notes",
    )
    parser.add_argument(
        "root_dir",
        type=Path,
        help="Root directory; each subdirectory becomes a notebook",
    )
    parser.add_argument("--email", required=True, help="Owning user's email")
    parser.add_argument(
        "--password",
        default=None,
        help=(
            "Owning user's password"
            " (or set NOTES_IMPORT_PASSWORD, or omit to be prompted)"
        ),
    )
    parser.add_argument(
        "--override",
        action="store_true",
        help=(
            "Also refresh notes edited since their import, and notes imported"
            " before import tracking existed (they are kept by default)"
        ),
    )
    parser.add_argument(
        "--include-web-clips",
        action="store_true",
        help="Also import web clippings (skipped by default)",
    )
    args = parser.parse_args()

    try:
        password = _resolve_password(args.password)
    except ValueError as exc:
        logger.error(str(exc))  # noqa: TRY400
        return 1

    session_factory = get_session_factory()
    with session_factory() as session:
        try:
            user = authenticate_user(session, email=args.email, password=password)
        except AuthError:
            logger.exception("Authentication failed")
            return 1

        import_source = HTMLFileImportSource(
            args.root_dir, include_web_clips=args.include_web_clips
        )
        report = run_import(session, import_source, user, override=args.override)
        _log_report(report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
