"""Tests for the migrate CLI (apply/revert Alembic migrations)."""

from unittest.mock import patch

from assistant.cli.migrate import main


def _run(argv: list[str]) -> int:
    with patch("sys.argv", ["migrate", *argv]):
        return main()


def test_upgrade_defaults_to_head() -> None:
    """Test that `upgrade` with no revision applies every pending migration."""
    with patch("assistant.cli.migrate.upgrade_database") as mock_upgrade:
        result = _run(["upgrade"])

        assert result == 0
        mock_upgrade.assert_called_once_with("head")


def test_upgrade_with_explicit_revision() -> None:
    """Test that `upgrade <revision>` passes the revision through."""
    with patch("assistant.cli.migrate.upgrade_database") as mock_upgrade:
        result = _run(["upgrade", "abc123"])

        assert result == 0
        mock_upgrade.assert_called_once_with("abc123")


def test_downgrade_defaults_to_one_step_back() -> None:
    """Test that `downgrade` with no revision reverts exactly one migration."""
    with patch("assistant.cli.migrate.downgrade_database") as mock_downgrade:
        result = _run(["downgrade"])

        assert result == 0
        mock_downgrade.assert_called_once_with("-1")


def test_downgrade_with_explicit_revision() -> None:
    """Test that `downgrade <revision>` passes the revision through."""
    with patch("assistant.cli.migrate.downgrade_database") as mock_downgrade:
        result = _run(["downgrade", "-2"])

        assert result == 0
        mock_downgrade.assert_called_once_with("-2")


def test_upgrade_failure_returns_one() -> None:
    """Test that an exception during upgrade is logged and returns 1, not raised."""
    with patch("assistant.cli.migrate.upgrade_database") as mock_upgrade:
        mock_upgrade.side_effect = Exception("boom")
        result = _run(["upgrade"])

        assert result == 1


def test_downgrade_failure_returns_one() -> None:
    """Test that an exception during downgrade is logged and returns 1, not raised."""
    with patch("assistant.cli.migrate.downgrade_database") as mock_downgrade:
        mock_downgrade.side_effect = Exception("boom")
        result = _run(["downgrade"])

        assert result == 1
