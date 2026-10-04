"""Swapping a user's authentication credential between providers.

Each user has exactly one credential. A swap replaces it in a single
flush: the old credential row is deleted, the new one inserted, and every
refresh token of the user is revoked so sessions opened with the old
credential end. The caller issues fresh tokens for the current browser.

Every swap emails the account owner, so a swap they didn't make (e.g.
from a session left open) doesn't go unnoticed.
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
from assistant.email.service import Email, send_best_effort_email
from assistant.email.templates import CREDENTIAL_CHANGED
from assistant.google_auth.exceptions import GoogleAccountCollisionError
from assistant.models.schema import Credential, EmailConfirmation, User, UserStatus
from assistant.notes.user_service import get_user

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session

AuthProvider = Literal["password", "google"]

_PROVIDER_NAMES: dict[AuthProvider, str] = {
    "password": "your email and a password",
    "google": "Google",
}


def _credential(
    session: Session, user_id: uuid.UUID, provider: AuthProvider
) -> Credential | None:
    return session.scalar(
        select(Credential).where(
            Credential.user_id == user_id, Credential.provider == provider
        )
    )


def _notify_credential_changed(user: User, provider: AuthProvider) -> None:
    """Tell the account owner their sign-in method changed (best effort)."""
    email = Email(
        recipient=user.email,
        subject="Your Assistant sign-in method was changed",
        template=CREDENTIAL_CHANGED,
        values={"firstname": user.firstname, "method": _PROVIDER_NAMES[provider]},
    )
    send_best_effort_email(email, context="credential change notification")


def get_auth_provider(session: Session, user_id: uuid.UUID) -> AuthProvider:
    """Return the provider of the user's (single) credential.

    Defaults to "password" for a user without any credential row, which
    only exists for users created through the bare POST /user endpoint.
    """
    if _credential(session, user_id, "google") is not None:
        return "google"
    return "password"


def google_swap_requires_password(session: Session, user_id: uuid.UUID) -> bool:
    """Whether swap_to_google needs the current password for this user.

    A still-PENDING account never proved it controls its email; Google
    just did. So the Google identity alone may claim it, and an
    unconfirmed registration can't lock the email's owner out.
    """
    return get_user(session, user_id).status != UserStatus.PENDING.value


def swap_to_google(
    session: Session,
    *,
    user_id: uuid.UUID,
    email: str,
    google_sub: str,
    password: str | None,
) -> User:
    """Replace the user's password credential with a Google credential.

    The caller has already verified the Google identity (google_sub,
    email). For an ACTIVE user, password proves ownership of the account
    being converted. A still-PENDING user needs no password (see
    google_swap_requires_password) and is activated, since Google
    verified the email.

    Raises CredentialSwapError if the user has no password credential or
    their email no longer matches the Google email. Raises AuthError if
    the password is required and missing or wrong. Raises
    GoogleAccountCollisionError if the Google identity is already bound
    to another user.
    """
    user = get_user(session, user_id)
    if user.email != email:
        raise CredentialSwapError
    credential = _credential(session, user_id, "password")
    if credential is None or credential.credential_hash is None:
        raise CredentialSwapError
    if google_swap_requires_password(session, user_id) and (
        password is None or not verify_password(credential.credential_hash, password)
    ):
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
    _notify_credential_changed(user, "google")
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
    _notify_credential_changed(user, "password")
    return user
