"""User service — User CRUD operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from assistant.invites.service import create_gated_user
from assistant.models.schema import User
from assistant.notes.exceptions import UserNotFoundError

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session


def create_user(  # noqa: PLR0913
    session: Session,
    email: str,
    firstname: str,
    lastname: str,
    *,
    invite_quota: int | None = None,
    invite_id: uuid.UUID | None = None,
) -> User:
    """The generic POST /user path — no Credential, matching today's
    behavior (a user created this way can't log in via any provider
    until one is added separately)."""
    user, _invite = create_gated_user(
        session,
        email=email,
        firstname=firstname,
        lastname=lastname,
        invite_id=invite_id,
        invite_quota_override=invite_quota,
    )
    return user


def delete_user(session: Session, uid: uuid.UUID) -> User:
    """Permanently delete a user and everything that cascades from them.

    Relies entirely on the cascade="all, delete-orphan" relationships
    already declared on User — notebooks/notes owned, entitlements held
    (including on others' subjects), credentials, refresh_tokens, and
    invites_sent. Does NOT touch Invite rows where this user's email is
    only the invitee (a plain string field, not an FK).
    """
    user = get_user(session, uid)
    session.delete(user)
    session.flush()
    return user


def get_user(
    session: Session,
    uid: uuid.UUID,
) -> User:
    user = session.get(User, uid)
    if user is None:
        raise UserNotFoundError(str(uid))
    return user


def get_user_by_email(
    session: Session,
    email: str,
) -> User:
    user = session.scalar(select(User).where(User.email == email))
    if user is None:
        raise UserNotFoundError(email)
    return user


def list_users(
    session: Session,
    *,
    offset: int = 0,
    limit: int | None = None,
) -> list[User]:
    stmt = select(User).offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt))


def update_user(
    session: Session,
    uid: uuid.UUID,
    *,
    email: str | None = None,
    firstname: str | None = None,
    lastname: str | None = None,
) -> User:
    user = get_user(session, uid)
    if email is not None:
        user.email = email
    if firstname is not None:
        user.firstname = firstname
    if lastname is not None:
        user.lastname = lastname
    session.flush()
    return user
