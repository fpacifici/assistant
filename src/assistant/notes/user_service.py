"""User service — User CRUD operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from assistant.models.schema import User
from assistant.notes.exceptions import UserNotFoundError

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session


def create_user(
    session: Session,
    email: str,
    firstname: str,
    lastname: str,
) -> User:
    user = User(email=email, firstname=firstname, lastname=lastname)
    session.add(user)
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
