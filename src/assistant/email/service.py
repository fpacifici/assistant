"""Email service — sends templated, text-only email via Mailgun."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import requests
from email_validator import EmailNotValidError, validate_email

from assistant.config import Config
from assistant.email.exceptions import (
    EmailSendError,
    EmailTemplateError,
    EmailValidationError,
)

if TYPE_CHECKING:
    import string

_TRANSIENT_STATUS_THRESHOLD = 500


@dataclass(frozen=True)
class Email:
    """An email to send: who it's for, its subject, and its templated body."""

    recipient: str
    subject: str
    template: string.Template
    values: dict[str, str]


def _validate_recipient(recipient: str) -> None:
    try:
        validate_email(recipient, check_deliverability=False)
    except EmailNotValidError as exc:
        raise EmailValidationError(recipient) from exc


def _render_body(template: string.Template, values: dict[str, str]) -> str:
    try:
        return template.substitute(values)
    except KeyError as exc:
        raise EmailTemplateError(str(exc)) from exc


def _post(
    url: str, *, apikey: str, data: dict[str, str], timeout: int
) -> requests.Response:
    return requests.post(url, auth=("api", apikey), data=data, timeout=timeout)


def send_email(email: Email) -> None:
    """Send an email through Mailgun.

    Raises:
        EmailValidationError: `email.recipient` is not a well-formed address.
        EmailTemplateError: `email.values` is missing a key the template needs.
        EmailSendError: Mailgun rejected the send, or the request failed
            after one retry on a transient error.
    """
    _validate_recipient(email.recipient)
    body = _render_body(email.template, email.values)

    app_config = Config()
    config = app_config.get_mailgun_config()
    domain = app_config.get_domain()
    url = f"{config['apiurl']}/{domain}/messages"
    data = {
        "from": config["sender"],
        "to": email.recipient,
        "subject": email.subject,
        "text": body,
    }

    attempts = 0
    while True:
        attempts += 1
        try:
            response = _post(
                url, apikey=config["apikey"], data=data, timeout=config["timeout"]
            )
        except requests.RequestException as exc:
            if attempts > 1:
                msg = f"Mailgun request failed: {exc}"
                raise EmailSendError(msg) from exc
            continue

        if response.ok:
            return

        if response.status_code < _TRANSIENT_STATUS_THRESHOLD or attempts > 1:
            msg = f"Mailgun send failed ({response.status_code}): {response.text}"
            raise EmailSendError(msg, status_code=response.status_code)
