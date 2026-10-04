"""Short-lived signed tokens handing a verified Google result from the
OAuth callback to a follow-up request.

The callback is a top-level redirect and can't ask the user anything, so
when it needs a follow-up step it stores what it verified in one of these
tokens (delivered as an HttpOnly cookie) and redirects to a page that
completes the step:

- swap: a password account's owner signed in with Google; the swap page
  confirms converting the account to Google sign-in.
- reauth: a Google user re-authenticated; the settings page may now
  switch the account to password sign-in.

The `purpose` claim keeps these tokens from being accepted for each
other, as an OAuth state, or as an access token (all share one secret).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from assistant.auth.service import jwt_secret
from assistant.google_auth.exceptions import GoogleHandoffTokenInvalidError

SWAP_TOKEN_TTL = timedelta(minutes=10)
REAUTH_TOKEN_TTL = timedelta(minutes=5)

_SWAP_PURPOSE = "google_swap"
_REAUTH_PURPOSE = "google_reauth"


@dataclass(frozen=True)
class SwapClaims:
    user_id: uuid.UUID
    email: str
    sub: str


def _sign(purpose: str, ttl: timedelta, claims: dict[str, Any]) -> str:
    payload = {**claims, "purpose": purpose, "exp": datetime.now(UTC) + ttl}
    return jwt.encode(payload, jwt_secret(), algorithm="HS256")


def _verify(purpose: str, raw: str | None) -> dict[str, Any]:
    if raw is None:
        raise GoogleHandoffTokenInvalidError
    try:
        payload: dict[str, Any] = jwt.decode(raw, jwt_secret(), algorithms=["HS256"])
    except jwt.InvalidTokenError as exc:
        raise GoogleHandoffTokenInvalidError from exc
    if payload.get("purpose") != purpose:
        raise GoogleHandoffTokenInvalidError
    return payload


def sign_swap_token(*, user_id: uuid.UUID, email: str, sub: str) -> str:
    return _sign(
        _SWAP_PURPOSE,
        SWAP_TOKEN_TTL,
        {"user_id": str(user_id), "email": email, "google_sub": sub},
    )


def verify_swap_token(raw: str | None) -> SwapClaims:
    payload = _verify(_SWAP_PURPOSE, raw)
    try:
        return SwapClaims(
            user_id=uuid.UUID(payload["user_id"]),
            email=payload["email"],
            sub=payload["google_sub"],
        )
    except (KeyError, ValueError) as exc:
        raise GoogleHandoffTokenInvalidError from exc


def sign_reauth_token(*, user_id: uuid.UUID) -> str:
    return _sign(_REAUTH_PURPOSE, REAUTH_TOKEN_TTL, {"user_id": str(user_id)})


def verify_reauth_token(raw: str | None) -> uuid.UUID:
    """Return the user id the reauth token was issued for."""
    payload = _verify(_REAUTH_PURPOSE, raw)
    try:
        return uuid.UUID(payload["user_id"])
    except (KeyError, ValueError) as exc:
        raise GoogleHandoffTokenInvalidError from exc
