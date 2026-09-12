"""All direct interaction with Google's OAuth2/OIDC endpoints, isolated
here — nothing else in the codebase talks to Google."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

import requests
from google.auth import exceptions as google_auth_exceptions
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from assistant.config import Config
from assistant.google_auth.exceptions import (
    GoogleTokenExchangeError,
    GoogleTokenInvalidError,
)


@dataclass(frozen=True)
class GoogleIdTokenClaims:
    sub: str
    email: str
    email_verified: bool
    given_name: str | None
    family_name: str | None


def redirect_uri(config: Config) -> str:
    """The Google OAuth redirect URI, composed from config.public_origin()
    (this app's single public origin, config-wide, already used for
    invite URLs) plus the Google-specific path.

    Used both when building the authorization URL and when exchanging
    the code — Google requires the two to match exactly.
    """
    return f"{config.public_origin()}{config.get_google_config()['redirect_path']}"


def build_authorization_url(*, state: str, nonce: str) -> str:
    """The URL to redirect the browser to for the consent screen.

    `prompt=select_account` forces the Google account chooser every time,
    so a shared/public machine with an existing Google session doesn't
    silently authenticate as the wrong person.
    """
    config = Config()
    google_config = config.get_google_config()
    params = {
        "client_id": google_config["client_id"],
        "redirect_uri": redirect_uri(config),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "prompt": "select_account",
    }
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"


def exchange_code_for_tokens(code: str) -> dict[str, str]:
    """POST the authorization code to Google's token endpoint.

    Raises GoogleTokenExchangeError on a network failure or a non-2xx
    response. No retry (unlike email/service.py's send_email) — this is
    a synchronous step in an interactive request, not a background job;
    on failure the user just clicks the button again.
    """
    config = Config()
    google_config = config.get_google_config()
    try:
        response = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": google_config["client_id"],
                "client_secret": google_config["client_secret"],
                "redirect_uri": redirect_uri(config),
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
    except requests.RequestException as exc:
        raise GoogleTokenExchangeError(str(exc)) from exc
    if not response.ok:
        msg = f"Google token endpoint returned {response.status_code}: {response.text}"
        raise GoogleTokenExchangeError(msg)
    return response.json()  # type: ignore[no-any-return]


def verify_id_token(raw_id_token: str, *, expected_nonce: str) -> GoogleIdTokenClaims:
    """Verify signature (against Google's JWKS), issuer, audience, and
    expiry via `google-auth`, then check the nonce ourselves (the library
    doesn't take a nonce param).

    Raises GoogleTokenInvalidError for any of: bad signature, wrong
    issuer/audience, expired token, or a nonce that doesn't match what
    google_auth.state signed for this attempt (replay protection).
    """
    config = Config().get_google_config()
    try:
        claims = google_id_token.verify_oauth2_token(
            raw_id_token,
            google_requests.Request(),
            audience=config["client_id"],
        )
    except (google_auth_exceptions.GoogleAuthError, ValueError) as exc:
        raise GoogleTokenInvalidError(str(exc)) from exc
    if claims.get("nonce") != expected_nonce:
        raise GoogleTokenInvalidError("nonce mismatch")  # noqa: TRY003
    return GoogleIdTokenClaims(
        sub=claims["sub"],
        email=claims["email"],
        email_verified=bool(claims.get("email_verified", False)),
        given_name=claims.get("given_name"),
        family_name=claims.get("family_name"),
    )
