"""Login-or-register from a verified Google ID token."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

from assistant.google_auth.exceptions import (
    GoogleAccountCollisionError,
    GoogleEmailNotVerifiedError,
    GooglePasswordAccountExistsError,
    GoogleReauthMismatchError,
    GoogleReauthStaleError,
)
from assistant.invites.service import create_gated_user
from assistant.models.schema import Credential, User
from assistant.notes.user_service import get_user

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session

    from assistant.google_auth.oauth import GoogleIdTokenClaims

# How recent a Google sign-in must be to count as a re-authentication.
REAUTH_MAX_AGE = timedelta(minutes=5)


def handle_google_callback(
    session: Session,
    *,
    claims: GoogleIdTokenClaims,
    invite_id: uuid.UUID | None,
) -> User:
    """Login-or-register from a verified Google ID token.

    Raises GoogleEmailNotVerifiedError if claims.email_verified is false.
    Raises GooglePasswordAccountExistsError if this email belongs to a
    password account (the caller may offer swapping it to Google), or
    GoogleAccountCollisionError if it belongs to a user whose credential
    can't be swapped (e.g. bound to a different Google identity).
    """
    if not claims.email_verified:
        raise GoogleEmailNotVerifiedError

    existing_credential = session.scalar(
        select(Credential).where(
            Credential.provider == "google",
            Credential.provider_subject == claims.sub,
        )
    )
    if existing_credential is not None:
        return get_user(session, existing_credential.user_id)

    existing_user = session.scalar(select(User).where(User.email == claims.email))
    if existing_user is not None:
        # A provider_subject match would have been caught above, so
        # reaching here means this email belongs to a *different*
        # credential — collision, not a returning Google user.
        has_password = session.scalar(
            select(Credential).where(
                Credential.user_id == existing_user.uid,
                Credential.provider == "password",
            )
        )
        if has_password is not None:
            raise GooglePasswordAccountExistsError(
                claims.email, user_id=existing_user.uid, sub=claims.sub
            )
        raise GoogleAccountCollisionError(claims.email)

    user, _invite = create_gated_user(
        session,
        email=claims.email,
        firstname=claims.given_name or "",
        lastname=claims.family_name or "",
        invite_id=invite_id,
    )

    credential = Credential(
        user_id=user.uid,
        provider="google",
        provider_subject=claims.sub,
    )
    session.add(credential)
    session.flush()
    return user


def verify_reauth(
    session: Session,
    *,
    claims: GoogleIdTokenClaims,
    user_id: uuid.UUID,
    require_auth_time: bool,
) -> None:
    """Check a re-authentication returned a recent sign-in of user_id.

    Raises GoogleReauthMismatchError if the Google identity isn't user_id's
    credential — including when the user has no Google credential at all.
    Raises GoogleReauthStaleError if `auth_time` is older than
    REAUTH_MAX_AGE, or missing while require_auth_time is set.
    """
    credential = session.scalar(
        select(Credential).where(
            Credential.provider == "google",
            Credential.provider_subject == claims.sub,
        )
    )
    if credential is None or credential.user_id != user_id:
        raise GoogleReauthMismatchError

    if claims.auth_time is None:
        if require_auth_time:
            raise GoogleReauthStaleError
        return
    signed_in_at = datetime.fromtimestamp(claims.auth_time, UTC)
    if datetime.now(UTC) - signed_in_at > REAUTH_MAX_AGE:
        raise GoogleReauthStaleError
