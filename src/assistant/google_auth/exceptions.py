"""Google authentication module exceptions."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid


class GoogleAuthFlowError(Exception):
    """Base exception for the google_auth module."""


class GoogleStateInvalidError(GoogleAuthFlowError):
    """The `state` param is missing, malformed, unsigned, or expired."""


class GoogleTokenExchangeError(GoogleAuthFlowError):
    """The authorization-code exchange with Google's token endpoint failed."""


class GoogleTokenInvalidError(GoogleAuthFlowError):
    """The ID token failed signature/issuer/audience/expiry/nonce validation."""


class GoogleEmailNotVerifiedError(GoogleAuthFlowError):
    """Google reported email_verified=false for this identity."""


class GoogleAccountCollisionError(GoogleAuthFlowError):
    """This email already belongs to a different provider's credential."""

    def __init__(self, email: str) -> None:
        self.email = email
        super().__init__(f"{email} is already registered with a different provider")


class GooglePasswordAccountExistsError(GoogleAccountCollisionError):
    """This email belongs to a password account, which can be swapped to Google.

    Carries the account and the verified Google identity so the caller
    can offer the swap without re-running the OAuth flow.
    """

    def __init__(self, email: str, *, user_id: uuid.UUID, sub: str) -> None:
        super().__init__(email)
        self.user_id = user_id
        self.sub = sub


class GoogleReauthMismatchError(GoogleAuthFlowError):
    """A re-authentication returned a Google identity of a different user."""


class GoogleReauthStaleError(GoogleAuthFlowError):
    """A re-authentication didn't prove a recent Google sign-in.

    Either Google's `auth_time` is too old (the account chooser reused an
    existing Google session), or it is missing while it is required.
    """


class GoogleHandoffTokenInvalidError(GoogleAuthFlowError):
    """A swap/reauth handoff token is missing, malformed, or expired."""
