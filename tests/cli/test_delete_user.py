"""Tests for the delete-user admin CLI."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from assistant.cli.delete_user import main
from assistant.invites.service import create_invite
from assistant.models.schema import Entitlement, Invite, Notebook, PermissionName, User
from assistant.notes.exceptions import UserNotFoundError
from assistant.notes.user_service import get_user_by_email

_REGISTRATION_CONFIG = {
    "registration_enabled": True,
    "invites_enabled": True,
    "default_quota": 5,
    "expiry_days": 1,
}


def _make_user(session: Session, email: str, *, quota: int = 5) -> User:
    user = User(email=email, firstname="A", lastname="B", invite_quota_remaining=quota)
    session.add(user)
    session.flush()
    return user


def _run(db_session: Session, argv: list[str]) -> None:
    with (
        patch(
            "assistant.cli.delete_user.get_session_factory",
            return_value=lambda: db_session,
        ),
        patch("sys.argv", ["delete_user", *argv]),
    ):
        main()


@pytest.fixture(autouse=True)
def _mock_send_invite_email():  # noqa: ANN202
    with patch("assistant.email.service.send_email") as mock_send:
        yield mock_send


def test_delete_user_cascades_notebooks_notes_and_entitlements(
    db_session: Session,
) -> None:
    owner = _make_user(db_session, "owner@example.com")
    other = _make_user(db_session, "other@example.com")
    notebook = Notebook(name="nb", owner_id=owner.uid)
    db_session.add(notebook)
    db_session.flush()
    entitlement = Entitlement(
        principal_id=other.uid,
        notebook_id=notebook.id,
        permission_name=PermissionName.VIEW_NOTEBOOK.value,
    )
    db_session.add(entitlement)
    db_session.flush()
    entitlement_id = entitlement.id
    notebook_id = notebook.id
    db_session.commit()

    _run(db_session, ["--email", "owner@example.com", "--yes"])

    assert db_session.get(Notebook, notebook_id) is None
    assert db_session.get(Entitlement, entitlement_id) is None
    with pytest.raises(UserNotFoundError):
        get_user_by_email(db_session, "owner@example.com")


def test_delete_user_leaves_invitee_only_invite_untouched(db_session: Session) -> None:
    sender = _make_user(db_session, "sender@example.com")
    invitee = _make_user(db_session, "invitee@example.com")
    invite, _ = create_invite(
        db_session, sender, "invitee@example.com", _REGISTRATION_CONFIG
    )
    invite_id = invite.id
    db_session.commit()

    _run(db_session, ["--email", "invitee@example.com", "--yes"])

    # invitee-only invite (email match, no FK) is left untouched
    assert db_session.get(Invite, invite_id) is not None
    assert db_session.get(User, invitee.uid) is None


def test_delete_user_removes_invites_sent(db_session: Session) -> None:
    sender = _make_user(db_session, "sender@example.com")
    invite, _ = create_invite(
        db_session, sender, "someone@example.com", _REGISTRATION_CONFIG
    )
    invite_id = invite.id
    db_session.commit()

    _run(db_session, ["--email", "sender@example.com", "--yes"])

    assert db_session.get(Invite, invite_id) is None


def test_delete_user_unknown_email_raises(db_session: Session) -> None:
    with pytest.raises(UserNotFoundError):
        _run(db_session, ["--email", "nobody@example.com", "--yes"])


def test_delete_user_without_yes_declines(db_session: Session) -> None:
    user = _make_user(db_session, "user@example.com")
    db_session.commit()

    with patch("builtins.input", return_value="n"):
        _run(db_session, ["--email", "user@example.com"])

    assert db_session.get(User, user.uid) is not None
