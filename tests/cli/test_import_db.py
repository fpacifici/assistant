"""Tests for import_db CLI script."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from assistant.cli.import_db import main


def test_import_db_cli_success(tmp_path: Path) -> None:
    """Test successful execution of import_db CLI."""

    archive_path = tmp_path / "backup.tar.gz"

    with (
        patch("assistant.cli.import_db.Config") as mock_config_cls,
        patch("assistant.cli.import_db.run_restore") as mock_run_restore,
        patch("sys.argv", ["import_db", str(archive_path)]),
    ):
        mock_config = MagicMock()
        mock_config_cls.return_value = mock_config
        result = main()

    assert result == 0
    mock_run_restore.assert_called_once()


def test_import_db_cli_failure(tmp_path: Path) -> None:
    """Test import_db CLI error handling."""

    archive_path = tmp_path / "backup.tar.gz"

    with (
        patch("assistant.cli.import_db.Config") as mock_config_cls,
        patch("assistant.cli.import_db.run_restore") as mock_run_restore,
        patch("sys.argv", ["import_db", str(archive_path)]),
    ):
        mock_config = MagicMock()
        mock_config_cls.return_value = mock_config
        mock_run_restore.side_effect = Exception("Test error")
        result = main()

    assert result == 1

