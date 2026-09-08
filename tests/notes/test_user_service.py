"""Tests for the User service module."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from assistant.invites.exceptions import RegistrationDisabledError
from assistant.invites.service import create_invite
from assistant.models.schema import (
    Entitlement,
    Invite,
    InviteState,
    Notebook,
    PermissionName,
    User,
)
from assistant.notes.exceptions import UserNotFoundError
from assistant.notes.user_service import create_user, delete_user, list_users

_REGISTRATION_CONFIG = {
    "registration_enabled": True,
    "invites_enabled": True,
    "default_quota": 5,
    "expiry_days": 1,
}


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


# --- create_user invite quota ---


def test_create_user_sets_default_quota(db_session: Session) -> None:
    user = create_user(db_session, email="a@test.com", firstname="A", lastname="B")
    assert user.invite_quota_remaining == 5


def test_create_user_invite_quota_override(db_session: Session) -> None:
    user = create_user(
        db_session, email="a@test.com", firstname="A", lastname="B", invite_quota=2
    )
    assert user.invite_quota_remaining == 2


def test_create_user_registration_disabled_without_invite_raises(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REGISTRATION_REGISTRATION_ENABLED", "false")
    with pytest.raises(RegistrationDisabledError):
        create_user(db_session, email="a@test.com", firstname="A", lastname="B")


def test_create_user_registration_disabled_with_valid_invite_succeeds(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    inviter = create_user(
        db_session, email="inviter@test.com", firstname="I", lastname="V"
    )
    invite = create_invite(db_session, inviter, "new@test.com", _REGISTRATION_CONFIG)

    monkeypatch.setenv("REGISTRATION_REGISTRATION_ENABLED", "false")
    user = create_user(
        db_session,
        email="new@test.com",
        firstname="N",
        lastname="U",
        invite_id=invite.id,
    )
    assert user.email == "new@test.com"
    db_session.refresh(invite)
    assert invite.state == InviteState.CONVERTED.value


def test_create_user_voids_pending_invites_for_email(db_session: Session) -> None:
    inviter = create_user(
        db_session, email="inviter@test.com", firstname="I", lastname="V"
    )
    invite = create_invite(db_session, inviter, "new@test.com", _REGISTRATION_CONFIG)
    assert inviter.invite_quota_remaining == 4

    create_user(db_session, email="new@test.com", firstname="N", lastname="U")

    db_session.refresh(invite)
    assert invite.state == InviteState.VOID.value
    assert inviter.invite_quota_remaining == 5


# --- delete_user ---


def test_delete_user_unknown_raises(db_session: Session) -> None:
    with pytest.raises(UserNotFoundError):
        delete_user(db_session, uuid.uuid4())


def test_delete_user_cascades_notebooks_notes_and_entitlements(
    db_session: Session,
) -> None:
    owner = _make_user(db_session, "owner@test.com")
    other = _make_user(db_session, "other@test.com")

    notebook = Notebook(name="nb1", owner_id=owner.uid)
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

    delete_user(db_session, owner.uid)

    assert db_session.get(Notebook, notebook_id) is None
    assert db_session.get(Entitlement, entitlement_id) is None


def test_delete_user_leaves_invitee_only_invite_untouched(db_session: Session) -> None:
    inviter = _make_user(db_session, "inviter@test.com")
    invitee = _make_user(db_session, "invitee@test.com")
    invite = create_invite(db_session, inviter, "invitee@test.com", _REGISTRATION_CONFIG)
    invite_id = invite.id

    delete_user(db_session, invitee.uid)

    assert db_session.get(Invite, invite_id) is not None
