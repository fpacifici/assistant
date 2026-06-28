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

from assistant.models.schema import Credential, RefreshToken, User

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_ph = PasswordHasher()

ACCESS_TOKEN_MINUTES = 15
REFRESH_TOKEN_DAYS = 7


class AuthError(Exception):
    """Raised when authentication fails."""


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


# --- User registration ---


def register_user(
    session: Session,
    *,
    email: str,
    password: str,
    firstname: str,
    lastname: str,
) -> User:
    """Create a user and a password credential. Raises AuthError on duplicate email."""
    user = User(email=email, firstname=firstname, lastname=lastname)
    session.add(user)
    session.flush()

    credential = Credential(
        user_id=user.uid,
        provider="password",
        credential_hash=_ph.hash(password),
    )
    session.add(credential)
    session.flush()
    return user


# --- Login ---


def authenticate_user(session: Session, *, email: str, password: str) -> User:
    """Verify email + password and return the User. Raises AuthError on failure."""
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
