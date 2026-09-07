"""Tests for the email service."""

from __future__ import annotations

import string
from unittest.mock import MagicMock, patch

import pytest
import requests

from assistant.config import MailgunConfig
from assistant.email.exceptions import (
    EmailSendError,
    EmailTemplateError,
    EmailValidationError,
)
from assistant.email.service import Email, send_email

_MAILGUN_CONFIG: MailgunConfig = {
    "apiurl": "https://api.mailgun.net/v3",
    "apikey": "key-123",
    "sender": "noreply@example.com",
    "timeout": 7,
}
_DOMAIN = "mg.example.com"
_EXPECTED_URL = f"{_MAILGUN_CONFIG['apiurl']}/{_DOMAIN}/messages"


@pytest.fixture(autouse=True)
def _mock_config() -> None:
    with (
        patch(
            "assistant.email.service.Config.get_mailgun_config",
            return_value=_MAILGUN_CONFIG,
        ),
        patch("assistant.email.service.Config.get_domain", return_value=_DOMAIN),
    ):
        yield


def _make_response(*, ok: bool, status_code: int, text: str = "") -> MagicMock:
    response = MagicMock(spec=requests.Response)
    response.ok = ok
    response.status_code = status_code
    response.text = text
    return response


def test_send_email_posts_expected_request() -> None:
    email = Email(
        recipient="user@example.com",
        subject="Hi",
        template=string.Template("Hello $name"),
        values={"name": "Ada"},
    )

    with patch("assistant.email.service.requests.post") as mock_post:
        mock_post.return_value = _make_response(ok=True, status_code=200)
        result = send_email(email)

    assert result is None
    mock_post.assert_called_once_with(
        _EXPECTED_URL,
        auth=("api", _MAILGUN_CONFIG["apikey"]),
        data={
            "from": _MAILGUN_CONFIG["sender"],
            "to": "user@example.com",
            "subject": "Hi",
            "text": "Hello Ada",
        },
        timeout=_MAILGUN_CONFIG["timeout"],
    )


def test_send_email_success_calls_post_once() -> None:
    email = Email(
        recipient="user@example.com",
        subject="Hi",
        template=string.Template("Hello $name"),
        values={"name": "Ada"},
    )

    with patch("assistant.email.service.requests.post") as mock_post:
        mock_post.return_value = _make_response(ok=True, status_code=200)
        assert send_email(email) is None

    assert mock_post.call_count == 1


def test_send_email_invalid_recipient_raises_before_post() -> None:
    email = Email(
        recipient="not-an-email",
        subject="Hi",
        template=string.Template("Hello $name"),
        values={"name": "Ada"},
    )

    with patch("assistant.email.service.requests.post") as mock_post:
        with pytest.raises(EmailValidationError):
            send_email(email)
        mock_post.assert_not_called()


def test_send_email_missing_template_value_raises_before_post() -> None:
    email = Email(
        recipient="user@example.com",
        subject="Hi",
        template=string.Template("Hello $name"),
        values={},
    )

    with patch("assistant.email.service.requests.post") as mock_post:
        with pytest.raises(EmailTemplateError):
            send_email(email)
        mock_post.assert_not_called()


def test_send_email_extra_template_values_still_succeeds() -> None:
    email = Email(
        recipient="user@example.com",
        subject="Hi",
        template=string.Template("Hello $name"),
        values={"name": "Ada", "unused": "value"},
    )

    with patch("assistant.email.service.requests.post") as mock_post:
        mock_post.return_value = _make_response(ok=True, status_code=200)
        assert send_email(email) is None


def test_send_email_single_transient_failure_then_success() -> None:
    email = Email(
        recipient="user@example.com",
        subject="Hi",
        template=string.Template("Hello $name"),
        values={"name": "Ada"},
    )

    with patch("assistant.email.service.requests.post") as mock_post:
        mock_post.side_effect = [
            requests.Timeout("timed out"),
            _make_response(ok=True, status_code=200),
        ]
        assert send_email(email) is None

    assert mock_post.call_count == 2


def test_send_email_two_transient_failures_raises_after_two_calls() -> None:
    email = Email(
        recipient="user@example.com",
        subject="Hi",
        template=string.Template("Hello $name"),
        values={"name": "Ada"},
    )

    with patch("assistant.email.service.requests.post") as mock_post:
        mock_post.side_effect = [
            requests.Timeout("timed out"),
            requests.Timeout("timed out again"),
        ]
        with pytest.raises(EmailSendError):
            send_email(email)

    assert mock_post.call_count == 2


def test_send_email_client_error_does_not_retry() -> None:
    email = Email(
        recipient="user@example.com",
        subject="Hi",
        template=string.Template("Hello $name"),
        values={"name": "Ada"},
    )

    with patch("assistant.email.service.requests.post") as mock_post:
        mock_post.return_value = _make_response(
            ok=False, status_code=401, text="bad api key"
        )
        with pytest.raises(EmailSendError) as exc_info:
            send_email(email)

    assert mock_post.call_count == 1
    assert exc_info.value.status_code == 401


def test_send_email_server_error_retries_once_then_raises() -> None:
    email = Email(
        recipient="user@example.com",
        subject="Hi",
        template=string.Template("Hello $name"),
        values={"name": "Ada"},
    )

    with patch("assistant.email.service.requests.post") as mock_post:
        mock_post.return_value = _make_response(
            ok=False, status_code=500, text="server error"
        )
        with pytest.raises(EmailSendError) as exc_info:
            send_email(email)

    assert mock_post.call_count == 2
    assert exc_info.value.status_code == 500


def test_send_email_passes_configured_timeout() -> None:
    email = Email(
        recipient="user@example.com",
        subject="Hi",
        template=string.Template("Hello $name"),
        values={"name": "Ada"},
    )

    with patch("assistant.email.service.requests.post") as mock_post:
        mock_post.return_value = _make_response(ok=True, status_code=200)
        send_email(email)

    assert mock_post.call_args.kwargs["timeout"] == _MAILGUN_CONFIG["timeout"]
