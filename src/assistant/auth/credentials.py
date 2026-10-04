"""Swapping a user's authentication credential between providers.

Each user has exactly one credential. A swap replaces it in a single
flush: the old credential row is deleted, the new one inserted, and every
refresh token of the user is revoked so sessions opened with the old
credential end. The caller issues fresh tokens for the current browser.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from sqlalchemy import select

from assistant.auth.exceptions import AuthError, CredentialSwapError
from assistant.auth.service import (
    hash_password,
    revoke_all_refresh_tokens,
    verify_password,
)
from assistant.google_auth.exceptions import GoogleAccountCollisionError
from assistant.models.schema import Credential, EmailConfirmation, User, UserStatus
from assistant.notes.user_service import get_user

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session

AuthProvider = Literal["password", "google"]


def _credential(
    session: Session, user_id: uuid.UUID, provider: AuthProvider
) -> Credential | None:
    return session.scalar(
        select(Credential).where(
            Credential.user_id == user_id, Credential.provider == provider
        )
    )


def get_auth_provider(session: Session, user_id: uuid.UUID) -> AuthProvider:
    """Return the provider of the user's (single) credential.

    Defaults to "password" for a user without any credential row, which
    only exists for users created through the bare POST /user endpoint.
    """
    if _credential(session, user_id, "google") is not None:
        return "google"
    return "password"


def swap_to_google(
    session: Session,
    *,
    user_id: uuid.UUID,
    email: str,
    google_sub: str,
    password: str,
) -> User:
    """Replace the user's password credential with a Google credential.

    The caller has already verified the Google identity (google_sub,
    email); password proves ownership of the account being converted.
    A still-PENDING user is activated, since Google verified the email.

    Raises CredentialSwapError if the user has no password credential or
    their email no longer matches the Google email. Raises AuthError if
    the password is wrong. Raises GoogleAccountCollisionError if the
    Google identity is already bound to another user.
    """
    user = get_user(session, user_id)
    if user.email != email:
        raise CredentialSwapError
    credential = _credential(session, user_id, "password")
    if credential is None or credential.credential_hash is None:
        raise CredentialSwapError
    if not verify_password(credential.credential_hash, password):
        raise AuthError("Invalid credentials")  # noqa: TRY003
    taken = session.scalar(
        select(Credential).where(
            Credential.provider == "google",
            Credential.provider_subject == google_sub,
        )
    )
    if taken is not None:
        raise GoogleAccountCollisionError(email)

    session.delete(credential)
    session.flush()
    session.add(
        Credential(user_id=user_id, provider="google", provider_subject=google_sub)
    )
    if user.status == UserStatus.PENDING.value:
        user.status = UserStatus.ACTIVE.value
        confirmation = session.get(EmailConfirmation, user_id)
        if confirmation is not None:
            session.delete(confirmation)
    revoke_all_refresh_tokens(session, user_id)
    session.flush()
    return user


def swap_to_password(session: Session, *, user_id: uuid.UUID, password: str) -> User:
    """Replace the user's Google credential with a password credential.

    The caller is responsible for having re-authenticated the user.
    Raises CredentialSwapError if the user doesn't sign in with Google.
    """
    user = get_user(session, user_id)
    credential = _credential(session, user_id, "google")
    if credential is None:
        raise CredentialSwapError

    session.delete(credential)
    session.flush()
    session.add(
        Credential(
            user_id=user_id,
            provider="password",
            credential_hash=hash_password(password),
        )
    )
    revoke_all_refresh_tokens(session, user_id)
    session.flush()
    return user
