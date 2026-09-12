"""Auth module exceptions."""

from __future__ import annotations


class AuthError(Exception):
    """Raised when authentication fails (bad credentials, invalid/expired token)."""


class AccountNotConfirmedError(Exception):
    """Credentials were correct but the account isn't confirmed yet.

    Deliberately NOT a subclass of AuthError — the login route maps it to
    a distinct 403 with a resend-confirmation action, not the generic 401
    'Invalid credentials' AuthError maps to.
    """


class ConfirmationTokenInvalidError(Exception):
    """Confirmation token doesn't exist, or (for a still-pending user) expired.

    Deliberately not distinguished — same one-reason precedent as
    invites.exceptions.InviteNotUsableError, and for the same purpose.
    """


class ConfirmationNotFoundError(Exception):
    """No PENDING user exists for this email (covers unknown + already-active)."""


class ConfirmationCooldownError(Exception):
    """A confirmation email was already sent within the resend cooldown window."""


class ConfirmationLimitExceededError(Exception):
    """This registration has already used all MAX_CONFIRMATION_SENDS attempts."""
