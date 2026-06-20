"""Tests for the User service module."""

from __future__ import annotations

from sqlalchemy.orm import Session

from assistant.models.schema import User
from assistant.notes.user_service import create_user, list_users


def _make_user(session: Session, email: str) -> User:
    return create_user(session, email=email, firstname="A", lastname="B")


def test_list_users_empty(db_session: Session) -> None:
    assert list_users(db_session) == []


def test_list_users_returns_all(db_session: Session) -> None:
    _make_user(db_session, "a@test.com")
    _make_user(db_session, "b@test.com")
    assert len(list_users(db_session)) == 2


def test_list_users_with_limit(db_session: Session) -> None:
    for i in range(3):
        _make_user(db_session, f"u{i}@test.com")
    assert len(list_users(db_session, limit=2)) == 2


def test_list_users_with_offset(db_session: Session) -> None:
    for i in range(3):
        _make_user(db_session, f"u{i}@test.com")
    assert len(list_users(db_session, offset=1)) == 2
