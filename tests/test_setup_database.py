"""Tests for setup_database script."""

from unittest.mock import patch

from assistant.setup_database import main


def test_setup_database_success() -> None:
    """Test successful database setup."""
    with patch("assistant.setup_database.init_database") as mock_init:
        mock_init.return_value = None
        result = main()
        assert result == 0
        mock_init.assert_called_once()


def test_setup_database_failure() -> None:
    """Test database setup failure handling."""
    with patch("assistant.setup_database.init_database") as mock_init:
        mock_init.side_effect = Exception("Database error")
        result = main()
        assert result == 1
        mock_init.assert_called_once()
