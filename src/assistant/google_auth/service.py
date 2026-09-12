"""Login-or-register from a verified Google ID token."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from assistant.google_auth.exceptions import (
    GoogleAccountCollisionError,
    GoogleEmailNotVerifiedError,
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
    Raises GoogleAccountCollisionError if this email belongs to a
    different provider's credential.
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
        # provider (password, today) — collision, not a returning
        # Google user.
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
