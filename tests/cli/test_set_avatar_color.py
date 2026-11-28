"""Tests for the set-avatar-color admin CLI."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from assistant.cli.set_avatar_color import main
from assistant.models.schema import User
from assistant.notes.avatar_colors import AVATAR_COLORS


def _make_user(session: Session) -> User:
    user = User(email="leda@example.com", firstname="Leda", lastname="L")
    session.add(user)
    session.flush()
    return user


def _color(session: Session, uid: uuid.UUID) -> str | None:
    """Re-read the user: the CLI closes the session, detaching earlier objects."""
    user = session.get(User, uid)
    assert user is not None
    return user.avatar_color


def _run(db_session: Session, argv: list[str]) -> int:
    with (
        patch(
            "assistant.cli.set_avatar_color.get_session_factory",
            return_value=lambda: db_session,
        ),
        patch("sys.argv", ["set_avatar_color", *argv]),
    ):
        return main()


def test_sets_the_color(db_session: Session) -> None:
    uid = _make_user(db_session).uid

    assert _run(db_session, ["--email", "leda@example.com", "--color", "pink"]) == 0

    assert _color(db_session, uid) == "pink"


def test_clear_forgets_the_color(db_session: Session) -> None:
    user = _make_user(db_session)
    user.avatar_color = "pink"
    uid = user.uid

    assert _run(db_session, ["--email", "leda@example.com", "--clear"]) == 0

    assert _color(db_session, uid) is None


def test_list_prints_the_palette(
    db_session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(db_session, ["--list"]) == 0

    out = capsys.readouterr().out
    for name, css in AVATAR_COLORS.items():
        assert name in out
        assert css in out


def test_unknown_email_fails(db_session: Session) -> None:
    assert _run(db_session, ["--email", "nobody@example.com", "--color", "pink"]) == 1


def test_rejects_a_color_not_in_the_palette(db_session: Session) -> None:
    user = _make_user(db_session)

    with pytest.raises(SystemExit):
        _run(db_session, ["--email", user.email, "--color", "chartreuse"])
    assert user.avatar_color is None


def test_requires_color_or_clear(db_session: Session) -> None:
    user = _make_user(db_session)

    with pytest.raises(SystemExit):
        _run(db_session, ["--email", user.email])
