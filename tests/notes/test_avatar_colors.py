"""Tests for avatar colours and the preferred-colour setting."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from assistant.models.schema import User
from assistant.notes.avatar_colors import AVATAR_COLORS, avatar_color
from assistant.notes.exceptions import UserNotFoundError
from assistant.notes.user_service import set_avatar_color


def _make_user(session: Session) -> User:
    user = User(email="leda@test.com", firstname="Leda", lastname="L")
    session.add(user)
    session.flush()
    return user


# --- avatar_color ---


def test_avatar_color_uses_the_preference() -> None:
    assert avatar_color(uuid.uuid4(), "pink") == AVATAR_COLORS["pink"]


def test_avatar_color_without_preference_is_stable_and_in_the_palette() -> None:
    uid = uuid.uuid4()

    assert avatar_color(uid, None) == avatar_color(uid, None)
    assert avatar_color(uid, None) in AVATAR_COLORS.values()


def test_avatar_color_ignores_a_name_not_in_the_palette() -> None:
    uid = uuid.uuid4()

    assert avatar_color(uid, "chartreuse") == avatar_color(uid, None)


def test_palette_spreads_users_over_every_colour() -> None:
    palette = list(AVATAR_COLORS.values())
    ids = [uuid.UUID(int=i) for i in range(len(palette))]

    assert {avatar_color(uid, None) for uid in ids} == set(palette)


# --- set_avatar_color ---


def test_set_avatar_color_stores_the_name(db_session: Session) -> None:
    user = _make_user(db_session)

    set_avatar_color(db_session, user.uid, "teal")

    assert db_session.get(User, user.uid).avatar_color == "teal"  # type: ignore[union-attr]


def test_set_avatar_color_none_clears_it(db_session: Session) -> None:
    user = _make_user(db_session)
    set_avatar_color(db_session, user.uid, "teal")

    set_avatar_color(db_session, user.uid, None)

    assert user.avatar_color is None


def test_set_avatar_color_rejects_an_unknown_name(db_session: Session) -> None:
    user = _make_user(db_session)

    with pytest.raises(ValueError, match="chartreuse"):
        set_avatar_color(db_session, user.uid, "chartreuse")
    assert user.avatar_color is None


def test_set_avatar_color_unknown_user(db_session: Session) -> None:
    with pytest.raises(UserNotFoundError):
        set_avatar_color(db_session, uuid.uuid4(), "teal")
