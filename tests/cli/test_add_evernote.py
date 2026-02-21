"""Tests for add_evernote CLI script."""

import json
from unittest.mock import MagicMock, patch

from assistant.cli.add_evernote import main
from assistant.models.schema import ExternalSource


def test_add_evernote_success() -> None:
    """Test adding an Evernote source with notebooks."""
    mock_session = MagicMock()
    mock_factory = MagicMock()
    mock_factory.return_value.__enter__ = MagicMock(return_value=mock_session)
    mock_factory.return_value.__exit__ = MagicMock(return_value=False)

    with (
        patch("assistant.cli.add_evernote.get_session_factory", return_value=mock_factory),
        patch("sys.argv", ["add_evernote", "Notebook1", "Notebook2"]),
    ):
        result = main()

    assert result == 0
    mock_session.add.assert_called_once()
    (added_source,) = mock_session.add.call_args[0]
    assert isinstance(added_source, ExternalSource)
    assert added_source.provider == "evernote"
    config = json.loads(added_source.provider_query)
    assert config == {"notebooks": ["Notebook1", "Notebook2"]}
    mock_session.commit.assert_called_once()


def test_add_evernote_failure() -> None:
    """Test add_evernote error handling."""
    mock_factory = MagicMock()
    mock_factory.return_value.__enter__ = MagicMock(
        side_effect=Exception("Database error")
    )
    mock_factory.return_value.__exit__ = MagicMock(return_value=False)

    with (
        patch("assistant.cli.add_evernote.get_session_factory", return_value=mock_factory),
        patch("sys.argv", ["add_evernote", "MyNotebook"]),
    ):
        result = main()

    assert result == 1
