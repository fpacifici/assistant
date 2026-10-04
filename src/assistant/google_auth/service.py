"""Login-or-register from a verified Google ID token."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from assistant.google_auth.exceptions import (
    GoogleAccountCollisionError,
    GoogleEmailNotVerifiedError,
    GooglePasswordAccountExistsError,
    GoogleReauthMismatchError,
)
from assistant.invites.service import create_gated_user
from assistant.models.schema import Credential, User
from assistant.notes.user_service import get_user

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session

    from assistant.google_auth.oauth import GoogleIdTokenClaims


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
    session: Session, *, claims: GoogleIdTokenClaims, user_id: uuid.UUID
) -> None:
    """Check a re-authentication returned the Google identity of user_id.

    Raises GoogleReauthMismatchError otherwise — including when the user
    has no Google credential at all.
    """
    credential = session.scalar(
        select(Credential).where(
            Credential.provider == "google",
            Credential.provider_subject == claims.sub,
        )
    )
    if credential is None or credential.user_id != user_id:
        raise GoogleReauthMismatchError
