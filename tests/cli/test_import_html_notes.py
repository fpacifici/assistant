"""Tests for the import_html_notes CLI script."""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from assistant.adapters.plugins.html_file import HTMLFileImportSource
from assistant.auth.service import AuthError
from assistant.cli.import_html_notes import main
from assistant.models.schema import User


def _mock_session_factory() -> tuple[MagicMock, MagicMock]:
    mock_session = MagicMock()
    mock_factory = MagicMock()
    mock_factory.return_value.__enter__ = MagicMock(return_value=mock_session)
    mock_factory.return_value.__exit__ = MagicMock(return_value=False)
    return mock_session, mock_factory


def _mock_user() -> User:
    return User(uid=uuid.uuid4(), email="u@test.com", firstname="A", lastname="B")


def _argv(tmp_path: Path, *extra: str) -> list[str]:
    return ["import_html_notes", str(tmp_path), "--email", "u@test.com", *extra]


# ---------------------------------------------------------------------------
# Password resolution precedence
# ---------------------------------------------------------------------------


def test_password_from_cli_argument(tmp_path: Path) -> None:
    _mock_session, mock_factory = _mock_session_factory()
    user = _mock_user()

    with (
        patch(
            "assistant.cli.import_html_notes.get_session_factory",
            return_value=mock_factory,
        ),
        patch(
            "assistant.cli.import_html_notes.authenticate_user",
            return_value=user,
        ) as mock_auth,
        patch("assistant.cli.import_html_notes.run_import") as mock_run_import,
        patch("sys.argv", _argv(tmp_path, "--password", "pw")),
    ):
        result = main()

    assert result == 0
    mock_auth.assert_called_once_with(
        mock_factory.return_value.__enter__.return_value,
        email="u@test.com",
        password="pw",
    )
    mock_run_import.assert_called_once()


def test_password_from_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_session, mock_factory = _mock_session_factory()
    user = _mock_user()
    monkeypatch.setenv("NOTES_IMPORT_PASSWORD", "envpw")

    with (
        patch(
            "assistant.cli.import_html_notes.get_session_factory",
            return_value=mock_factory,
        ),
        patch(
            "assistant.cli.import_html_notes.authenticate_user",
            return_value=user,
        ) as mock_auth,
        patch("assistant.cli.import_html_notes.run_import"),
        patch("sys.argv", _argv(tmp_path)),
    ):
        result = main()

    assert result == 0
    _, kwargs = mock_auth.call_args
    assert kwargs["password"] == "envpw"


def test_password_from_interactive_prompt_when_neither_supplied(
    tmp_path: Path,
) -> None:
    _mock_session, mock_factory = _mock_session_factory()
    user = _mock_user()

    with (
        patch(
            "assistant.cli.import_html_notes.get_session_factory",
            return_value=mock_factory,
        ),
        patch(
            "assistant.cli.import_html_notes.authenticate_user",
            return_value=user,
        ) as mock_auth,
        patch("assistant.cli.import_html_notes.run_import"),
        patch(
            "assistant.cli.import_html_notes.getpass.getpass",
            return_value="promptedpw",
        ),
        patch("sys.argv", _argv(tmp_path)),
    ):
        result = main()

    assert result == 0
    _, kwargs = mock_auth.call_args
    assert kwargs["password"] == "promptedpw"


def test_both_password_argument_and_env_var_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_session, mock_factory = _mock_session_factory()
    monkeypatch.setenv("NOTES_IMPORT_PASSWORD", "envpw")

    with (
        patch(
            "assistant.cli.import_html_notes.get_session_factory",
            return_value=mock_factory,
        ),
        patch("assistant.cli.import_html_notes.authenticate_user") as mock_auth,
        patch("assistant.cli.import_html_notes.run_import") as mock_run_import,
        patch("sys.argv", _argv(tmp_path, "--password", "pw")),
    ):
        result = main()

    assert result == 1
    mock_auth.assert_not_called()
    mock_run_import.assert_not_called()


# ---------------------------------------------------------------------------
# Argument forwarding
# ---------------------------------------------------------------------------


def test_override_flag_forwarded_as_true(tmp_path: Path) -> None:
    _mock_session, mock_factory = _mock_session_factory()
    user = _mock_user()

    with (
        patch(
            "assistant.cli.import_html_notes.get_session_factory",
            return_value=mock_factory,
        ),
        patch("assistant.cli.import_html_notes.authenticate_user", return_value=user),
        patch("assistant.cli.import_html_notes.run_import") as mock_run_import,
        patch("sys.argv", _argv(tmp_path, "--password", "pw", "--override")),
    ):
        main()

    _, kwargs = mock_run_import.call_args
    assert kwargs["override"] is True


def test_override_flag_defaults_false(tmp_path: Path) -> None:
    _mock_session, mock_factory = _mock_session_factory()
    user = _mock_user()

    with (
        patch(
            "assistant.cli.import_html_notes.get_session_factory",
            return_value=mock_factory,
        ),
        patch("assistant.cli.import_html_notes.authenticate_user", return_value=user),
        patch("assistant.cli.import_html_notes.run_import") as mock_run_import,
        patch("sys.argv", _argv(tmp_path, "--password", "pw")),
    ):
        main()

    _, kwargs = mock_run_import.call_args
    assert kwargs["override"] is False


def test_authenticated_user_uid_forwarded_to_run_import(tmp_path: Path) -> None:
    _mock_session, mock_factory = _mock_session_factory()
    user = _mock_user()

    with (
        patch(
            "assistant.cli.import_html_notes.get_session_factory",
            return_value=mock_factory,
        ),
        patch("assistant.cli.import_html_notes.authenticate_user", return_value=user),
        patch("assistant.cli.import_html_notes.run_import") as mock_run_import,
        patch("sys.argv", _argv(tmp_path, "--password", "pw")),
    ):
        main()

    args, _kwargs = mock_run_import.call_args
    owner_id = args[2]
    assert owner_id == user.uid


def test_html_file_import_source_constructed_from_root_dir(tmp_path: Path) -> None:
    _mock_session, mock_factory = _mock_session_factory()
    user = _mock_user()

    with (
        patch(
            "assistant.cli.import_html_notes.get_session_factory",
            return_value=mock_factory,
        ),
        patch("assistant.cli.import_html_notes.authenticate_user", return_value=user),
        patch("assistant.cli.import_html_notes.run_import") as mock_run_import,
        patch("sys.argv", _argv(tmp_path, "--password", "pw")),
    ):
        main()

    args, _kwargs = mock_run_import.call_args
    import_source = args[1]
    assert isinstance(import_source, HTMLFileImportSource)


# ---------------------------------------------------------------------------
# Auth failure
# ---------------------------------------------------------------------------


def test_auth_error_returns_one(tmp_path: Path) -> None:
    _mock_session, mock_factory = _mock_session_factory()

    with (
        patch(
            "assistant.cli.import_html_notes.get_session_factory",
            return_value=mock_factory,
        ),
        patch(
            "assistant.cli.import_html_notes.authenticate_user",
            side_effect=AuthError("Invalid credentials"),
        ),
        patch("assistant.cli.import_html_notes.run_import") as mock_run_import,
        patch("sys.argv", _argv(tmp_path, "--password", "pw")),
    ):
        result = main()

    assert result == 1
    mock_run_import.assert_not_called()
