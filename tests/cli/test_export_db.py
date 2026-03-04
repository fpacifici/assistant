"""Tests for export_db CLI script."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from assistant.cli.export_db import main


def test_export_db_cli_success(tmp_path: Path) -> None:
    """Test successful execution of export_db CLI."""

    output_path = tmp_path / "backup.tar.gz"

    with (
        patch("assistant.cli.export_db.Config") as mock_config_cls,
        patch("assistant.cli.export_db.run_export") as mock_run_export,
        patch("sys.argv", ["export_db", str(output_path)]),
    ):
        mock_config = MagicMock()
        mock_config_cls.return_value = mock_config
        result = main()

    assert result == 0
    mock_run_export.assert_called_once()


def test_export_db_cli_failure(tmp_path: Path) -> None:
    """Test export_db CLI error handling."""

    output_path = tmp_path / "backup.tar.gz"

    with (
        patch("assistant.cli.export_db.Config") as mock_config_cls,
        patch("assistant.cli.export_db.run_export") as mock_run_export,
        patch("sys.argv", ["export_db", str(output_path)]),
    ):
        mock_config = MagicMock()
        mock_config_cls.return_value = mock_config
        mock_run_export.side_effect = Exception("Test error")
        result = main()

    assert result == 1

