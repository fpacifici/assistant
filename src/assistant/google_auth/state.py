"""Sign/verify the OAuth `state` param — the only place round-trip data
(the CSRF nonce and, for the invite flow, which invite) survives between
`GET /auth/google` and `GET /auth/google/callback`, since this backend
keeps no server-side session."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from assistant.auth.service import jwt_secret
from assistant.google_auth.exceptions import GoogleStateInvalidError

STATE_TTL_MINUTES = 10


@dataclass(frozen=True)
class GoogleStateClaims:
    nonce: str
    invite_id: uuid.UUID | None
    # Set when a logged-in user re-authenticates (before a sensitive
    # change) instead of logging in.
    reauth_user_id: uuid.UUID | None = None


def sign_state(
    *,
    nonce: str,
    invite_id: uuid.UUID | None,
    reauth_user_id: uuid.UUID | None = None,
) -> str:
    payload = {
        "nonce": nonce,
        "invite_id": str(invite_id) if invite_id else None,
        "reauth_user_id": str(reauth_user_id) if reauth_user_id else None,
        "exp": datetime.now(UTC) + timedelta(minutes=STATE_TTL_MINUTES),
    }
    return jwt.encode(payload, jwt_secret(), algorithm="HS256")


def verify_state(raw: str) -> GoogleStateClaims:
    try:
        payload = jwt.decode(raw, jwt_secret(), algorithms=["HS256"])
    except jwt.InvalidTokenError as exc:
        raise GoogleStateInvalidError from exc
    if "nonce" not in payload:
        raise GoogleStateInvalidError
    invite_id = uuid.UUID(payload["invite_id"]) if payload.get("invite_id") else None
    reauth_user_id = (
        uuid.UUID(payload["reauth_user_id"]) if payload.get("reauth_user_id") else None
    )
    return GoogleStateClaims(
        nonce=payload["nonce"], invite_id=invite_id, reauth_user_id=reauth_user_id
    )
