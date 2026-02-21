"""Tests for drop_database script."""

from unittest.mock import patch

from assistant.cli.drop_database import main


def test_drop_database_success() -> None:
    """Test successful database drop."""
    with patch("assistant.cli.drop_database.drop_database") as mock_drop:
        mock_drop.return_value = None
        result = main()
        assert result == 0
        mock_drop.assert_called_once()


def test_drop_database_failure() -> None:
    """Test database drop failure handling."""
    with patch("assistant.cli.drop_database.drop_database") as mock_drop:
        mock_drop.side_effect = Exception("Drop error")
        result = main()
        assert result == 1
        mock_drop.assert_called_once()
