"""Authentication service — registration, login, token lifecycle."""

from __future__ import annotations

import hashlib
import os
import secrets
import uuid as uuid_module
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import delete, select

from assistant.auth.exceptions import (
    AccountNotConfirmedError,
    AuthError,
    ConfirmationCooldownError,
    ConfirmationLimitExceededError,
    ConfirmationNotFoundError,
    ConfirmationTokenInvalidError,
)
from assistant.config import Config
from assistant.email.service import Email, send_best_effort_email
from assistant.email.templates import CONFIRM_REGISTRATION
from assistant.invites.service import (
    default_quota_for_new_user,
    on_user_created,
    resolve_registration_gate,
)
from assistant.models.schema import (
    Credential,
    EmailConfirmation,
    RefreshToken,
    User,
    UserStatus,
)
from assistant.urls import confirm_email_url

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_ph = PasswordHasher()

ACCESS_TOKEN_MINUTES = 15
REFRESH_TOKEN_DAYS = 7

CONFIRMATION_TOKEN_TTL = timedelta(hours=24)
CONFIRMATION_RESEND_COOLDOWN = timedelta(minutes=5)
MAX_CONFIRMATION_SENDS = 3


def _jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET", "")
    if not secret:
        msg = "JWT_SECRET environment variable is not set"
        raise RuntimeError(msg)
    return secret


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# --- Token creation ---


def create_access_token(user_id: uuid_module.UUID) -> str:
    """Return a signed JWT access token for the given user."""
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_MINUTES),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm="HS256")


def decode_access_token(token: str) -> uuid_module.UUID:
    """Validate a JWT and return the user UUID from the sub claim."""
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
        return uuid_module.UUID(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
        raise AuthError("Invalid or expired access token") from exc  # noqa: TRY003


def _create_refresh_token(
    session: Session,
    user_id: uuid_module.UUID,
    family_id: uuid_module.UUID,
) -> str:
    raw = secrets.token_urlsafe(32)
    rt = RefreshToken(
        user_id=user_id,
        family_id=family_id,
        token_hash=_hash_token(raw),
        expires_at=datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_DAYS),
    )
    session.add(rt)
    session.flush()
    return raw


# --- Email confirmation ---


def _send_confirmation_email_best_effort(user: User, raw_token: str) -> bool:
    """Send the confirmation email synchronously; log-and-continue on failure.

    Returns whether the send succeeded. Never raises — the core
    registration/resend operation isn't hostage to Mailgun (grilling
    decision, applied identically to invites and sharing).
    """
    email = Email(
        recipient=user.email,
        subject="Confirm your Assistant account",
        template=CONFIRM_REGISTRATION,
        values={
            "firstname": user.firstname,
            "url": confirm_email_url(raw_token, Config()),
        },
    )
    return send_best_effort_email(email, context="confirmation email")


def create_email_confirmation(session: Session, user_id: uuid_module.UUID) -> str:
    """Create or overwrite the (one, per-user) pending EmailConfirmation row.

    Returns the raw token. Used both for the initial send (register_user)
    and for resend_confirmation — 'issue a fresh token and reset the
    clock' is exactly the same operation either way, so both share this.
    """
    raw = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    confirmation = session.get(EmailConfirmation, user_id)
    if confirmation is None:
        confirmation = EmailConfirmation(user_id=user_id, resend_count=0)
        session.add(confirmation)
    confirmation.token_hash = _hash_token(raw)
    confirmation.expires_at = now + CONFIRMATION_TOKEN_TTL
    confirmation.last_sent_at = now
    confirmation.resend_count += 1
    session.flush()
    return raw


def _reap_expired_pending_registration(session: Session, email: str) -> None:
    """Delete a stale, expired PENDING user for this email, if any.

    The entire 'lazy cleanup' mechanism — no background sweep. A still-live
    pending registration (not yet expired) is left alone; the subsequent
    INSERT hits the existing unique-email constraint and surfaces as the
    same 409 duplicate-email response an active user would produce.
    """
    existing = session.scalar(select(User).where(User.email == email))
    if existing is None or existing.status != UserStatus.PENDING.value:
        return
    confirmation = session.get(EmailConfirmation, existing.uid)
    now = datetime.now(UTC)
    if confirmation is not None and confirmation.expires_at.replace(tzinfo=UTC) >= now:
        return
    session.delete(existing)
    session.flush()


def confirm_email(session: Session, raw_token: str) -> User:
    """Activate the account raw_token was issued for.

    Idempotent: a token whose user is already ACTIVE returns that user
    without error — a second click on the same link is not a failure.
    Raises ConfirmationTokenInvalidError if the token doesn't exist, or
    (for a still-PENDING user) has expired — deliberately not
    distinguished from each other, same as InviteNotUsableError.
    """
    confirmation = session.scalar(
        select(EmailConfirmation).where(
            EmailConfirmation.token_hash == _hash_token(raw_token)
        )
    )
    if confirmation is None:
        raise ConfirmationTokenInvalidError
    user = session.get(User, confirmation.user_id)
    if user is None:
        raise ConfirmationTokenInvalidError
    if user.status == UserStatus.ACTIVE.value:
        return user
    if confirmation.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        raise ConfirmationTokenInvalidError
    user.status = UserStatus.ACTIVE.value
    session.flush()
    return user


def resend_confirmation(session: Session, email: str) -> bool:
    """Issue a fresh confirmation token + email for a still-pending registration.

    Returns confirmation_email_sent, same best-effort contract as
    registration. Raises ConfirmationNotFoundError if no PENDING user
    exists for this email (covers both 'no such user' and 'already
    confirmed' — not distinguished, same reasoning as
    ConfirmationTokenInvalidError). Raises ConfirmationCooldownError if
    the last send was under CONFIRMATION_RESEND_COOLDOWN ago. Raises
    ConfirmationLimitExceededError once MAX_CONFIRMATION_SENDS is used —
    the only recovery then is to let the 24h window lapse and register
    again (_reap_expired_pending_registration).
    """
    user = session.scalar(select(User).where(User.email == email))
    if user is None or user.status != UserStatus.PENDING.value:
        raise ConfirmationNotFoundError
    confirmation = session.get(EmailConfirmation, user.uid)
    if confirmation is None:
        raise ConfirmationNotFoundError

    now = datetime.now(UTC)
    last_sent = confirmation.last_sent_at.replace(tzinfo=UTC)
    if now - last_sent < CONFIRMATION_RESEND_COOLDOWN:
        raise ConfirmationCooldownError
    if confirmation.resend_count >= MAX_CONFIRMATION_SENDS:
        raise ConfirmationLimitExceededError

    raw_token = create_email_confirmation(session, user.uid)
    return _send_confirmation_email_best_effort(user, raw_token)


# --- User registration ---


def register_user(  # noqa: PLR0913
    session: Session,
    *,
    email: str,
    password: str,
    firstname: str,
    lastname: str,
    invite_id: uuid_module.UUID | None = None,
) -> tuple[User, bool]:
    """Create a user (PENDING) and a password credential; send confirmation.

    Returns (user, confirmation_email_sent) — registration never fails
    just because the send did. Raises AuthError on duplicate email. Raises
    RegistrationDisabledError if registration_enabled is false and no
    invite_id was given. Raises InvitesDisabledError /
    InviteNotUsableError / InviteEmailMismatchError per
    get_valid_pending_invite and the email-match check, when an invite_id
    is given.
    """
    config = Config().get_registration_config()
    invite = resolve_registration_gate(session, config, email, invite_id)
    _reap_expired_pending_registration(session, email)

    user = User(
        email=email,
        firstname=firstname,
        lastname=lastname,
        status=UserStatus.PENDING.value,
        invite_quota_remaining=default_quota_for_new_user(config, None),
    )
    session.add(user)
    session.flush()

    credential = Credential(
        user_id=user.uid,
        provider="password",
        credential_hash=_ph.hash(password),
    )
    session.add(credential)
    session.flush()

    on_user_created(session, user, used_invite_id=invite.id if invite else None)

    raw_token = create_email_confirmation(session, user.uid)
    email_sent = _send_confirmation_email_best_effort(user, raw_token)
    return user, email_sent


# --- Login ---


def authenticate_user(session: Session, *, email: str, password: str) -> User:
    """Verify email + password and return the User.

    Raises AuthError on failure. Raises AccountNotConfirmedError (checked
    after credential verification, so we never leak account state before
    proving the password) if the credentials are correct but the account
    is still PENDING.
    """
    stmt = (
        select(User)
        .join(Credential, Credential.user_id == User.uid)
        .where(User.email == email)
        .where(Credential.provider == "password")
    )
    user = session.scalar(stmt)
    if user is None:
        raise AuthError("Invalid credentials")  # noqa: TRY003

    cred_stmt = (
        select(Credential)
        .where(Credential.user_id == user.uid)
        .where(Credential.provider == "password")
    )
    credential = session.scalar(cred_stmt)
    if credential is None or credential.credential_hash is None:
        raise AuthError("Invalid credentials")  # noqa: TRY003

    try:
        _ph.verify(credential.credential_hash, password)
    except VerifyMismatchError as exc:
        raise AuthError("Invalid credentials") from exc  # noqa: TRY003

    if user.status != UserStatus.ACTIVE.value:
        raise AccountNotConfirmedError

    return user


def issue_tokens(session: Session, user_id: uuid_module.UUID) -> tuple[str, str]:
    """Create and return (access_token, refresh_token) for the user."""
    family_id = uuid_module.uuid4()
    access = create_access_token(user_id)
    refresh = _create_refresh_token(session, user_id, family_id)
    return access, refresh


# --- Refresh ---


def rotate_refresh_token(
    session: Session, raw_token: str
) -> tuple[uuid_module.UUID, str, str]:
    """Exchange a refresh token for a new access + refresh pair.

    Returns (user_id, new_access_token, new_refresh_token).
    Raises AuthError if the token is invalid or expired.
    """
    token_hash = _hash_token(raw_token)
    rt = session.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))

    if rt is None:
        raise AuthError("Invalid refresh token")  # noqa: TRY003

    now = datetime.now(UTC)
    if rt.expires_at.replace(tzinfo=UTC) < now:
        session.delete(rt)
        raise AuthError("Refresh token expired")  # noqa: TRY003

    user_id = rt.user_id
    family_id = rt.family_id

    session.delete(rt)
    session.flush()

    new_access = create_access_token(user_id)
    new_refresh = _create_refresh_token(session, user_id, family_id)
    return user_id, new_access, new_refresh


# --- Logout ---


def logout_user(session: Session, raw_token: str) -> None:
    """Delete the refresh token family, invalidating all tokens for that session."""
    token_hash = _hash_token(raw_token)
    rt = session.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    if rt is None:
        return
    session.execute(delete(RefreshToken).where(RefreshToken.family_id == rt.family_id))
