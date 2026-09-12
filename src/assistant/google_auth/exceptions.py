"""Google authentication module exceptions."""

from __future__ import annotations


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
