"""Tests for load_data CLI script."""

from unittest.mock import MagicMock, patch

from assistant.cli.load_data import main


def test_load_data_cli_success() -> None:
    """Test successful execution of load_data CLI."""
    with (
        patch("assistant.cli.load_data.load_data") as mock_load_data,
        patch("assistant.cli.load_data._register_plugins"),
        patch("assistant.cli.load_data.Config") as mock_config,
        patch("sys.argv", ["load_data"]),
    ):
        mock_load_data.return_value = None
        mock_config.return_value = MagicMock()
        result = main()
        assert result == 0
        mock_load_data.assert_called_once()


def test_load_data_cli_failure() -> None:
    """Test load_data CLI error handling."""
    with (
        patch("assistant.cli.load_data.load_data") as mock_load_data,
        patch("assistant.cli.load_data._register_plugins"),
        patch("assistant.cli.load_data.Config") as mock_config,
        patch("sys.argv", ["load_data"]),
    ):
        mock_load_data.side_effect = Exception("Test error")
        mock_config.return_value = MagicMock()
        result = main()
        assert result == 1
