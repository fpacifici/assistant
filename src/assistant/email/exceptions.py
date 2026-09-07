"""Email-service-specific exceptions."""

from __future__ import annotations


class EmailValidationError(Exception):
    """Raised when a recipient address fails format validation."""

    def __init__(self, address: str) -> None:
        super().__init__(f"Invalid email address: {address}")
        self.address = address


class EmailTemplateError(Exception):
    """Raised when template substitution is missing a required value."""

    def __init__(self, missing_key: str) -> None:
        super().__init__(f"Missing template value: {missing_key}")
        self.missing_key = missing_key


class EmailSendError(Exception):
    """Raised when Mailgun rejects the send or the request fails outright."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
