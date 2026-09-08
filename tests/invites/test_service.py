"""Tests for the invites service module."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from assistant.config import RegistrationConfig
from assistant.invites.exceptions import (
    InviteNotUsableError,
    InvitePermissionError,
    InvitesDisabledError,
    QuotaExhaustedError,
)
from assistant.invites.service import (
    admin_create_invite,
    admin_void_invite,
    convert_invite,
    create_invite,
    delete_invite,
    get_valid_pending_invite,
    on_user_created,
    replenish_quota,
    void_invite,
)
from assistant.models.schema import Invite, InviteState, User

_ENABLED_CONFIG: RegistrationConfig = {
    "registration_enabled": True,
    "invites_enabled": True,
    "default_quota": 5,
    "expiry_days": 1,
}

_DISABLED_INVITES_CONFIG: RegistrationConfig = {
    **_ENABLED_CONFIG,
    "invites_enabled": False,
}


def _make_user(session: Session, email: str, *, quota: int = 5) -> User:
    user = User(
        email=email,
        firstname="A",
        lastname="B",
        invite_quota_remaining=quota,
    )
    session.add(user)
    session.flush()
    return user


def _make_invite(  # noqa: PLR0913
    session: Session,
    *,
    inviter: User,
    email: str = "invitee@example.com",
    state: InviteState = InviteState.PENDING,
    quota_consumed: bool = True,
    expires_at: datetime | None = None,
) -> Invite:
    invite = Invite(
        invitee_email=email,
        inviter_id=inviter.uid,
        state=state.value,
        quota_consumed=quota_consumed,
        expires_at=expires_at or (datetime.now(UTC) + timedelta(days=1)),
    )
    session.add(invite)
    session.flush()
    return invite


# --- create_invite ---


def test_create_invite_decrements_quota_and_sets_quota_consumed(
    db_session: Session,
) -> None:
    inviter = _make_user(db_session, "inviter@example.com", quota=5)
    invite = create_invite(db_session, inviter, "invitee@example.com", _ENABLED_CONFIG)

    assert inviter.invite_quota_remaining == 4
    assert invite.quota_consumed is True
    assert invite.state == InviteState.PENDING.value
    assert invite.invitee_email == "invitee@example.com"


def test_create_invite_raises_when_quota_exhausted(db_session: Session) -> None:
    inviter = _make_user(db_session, "inviter@example.com", quota=0)
    with pytest.raises(QuotaExhaustedError):
        create_invite(db_session, inviter, "invitee@example.com", _ENABLED_CONFIG)


def test_create_invite_raises_when_invites_disabled(db_session: Session) -> None:
    inviter = _make_user(db_session, "inviter@example.com", quota=5)
    with pytest.raises(InvitesDisabledError):
        create_invite(
            db_session, inviter, "invitee@example.com", _DISABLED_INVITES_CONFIG
        )


def test_create_invite_never_idempotent(db_session: Session) -> None:
    inviter = _make_user(db_session, "inviter@example.com", quota=5)
    first = create_invite(db_session, inviter, "invitee@example.com", _ENABLED_CONFIG)
    second = create_invite(db_session, inviter, "invitee@example.com", _ENABLED_CONFIG)

    assert first.id != second.id
    assert inviter.invite_quota_remaining == 3


# --- admin_create_invite ---


def test_admin_create_invite_never_touches_quota(db_session: Session) -> None:
    inviter = _make_user(db_session, "inviter@example.com", quota=5)
    invite = admin_create_invite(
        db_session, inviter, "invitee@example.com", _DISABLED_INVITES_CONFIG
    )

    assert inviter.invite_quota_remaining == 5
    assert invite.quota_consumed is False
    assert invite.state == InviteState.PENDING.value


# --- get_valid_pending_invite ---


def test_get_valid_pending_invite_succeeds_for_pending_unexpired(
    db_session: Session,
) -> None:
    inviter = _make_user(db_session, "inviter@example.com")
    invite = _make_invite(db_session, inviter=inviter)

    result = get_valid_pending_invite(db_session, invite.id, _ENABLED_CONFIG)
    assert result.id == invite.id


def test_get_valid_pending_invite_raises_for_missing(db_session: Session) -> None:
    with pytest.raises(InviteNotUsableError):
        get_valid_pending_invite(db_session, uuid.uuid4(), _ENABLED_CONFIG)


@pytest.mark.parametrize("state", [InviteState.VOID, InviteState.CONVERTED])
def test_get_valid_pending_invite_raises_for_non_pending(
    db_session: Session, state: InviteState
) -> None:
    inviter = _make_user(db_session, "inviter@example.com")
    invite = _make_invite(db_session, inviter=inviter, state=state)

    with pytest.raises(InviteNotUsableError):
        get_valid_pending_invite(db_session, invite.id, _ENABLED_CONFIG)


def test_get_valid_pending_invite_raises_for_expired(db_session: Session) -> None:
    inviter = _make_user(db_session, "inviter@example.com")
    invite = _make_invite(
        db_session,
        inviter=inviter,
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )

    with pytest.raises(InviteNotUsableError):
        get_valid_pending_invite(db_session, invite.id, _ENABLED_CONFIG)


def test_get_valid_pending_invite_raises_when_invites_disabled(
    db_session: Session,
) -> None:
    inviter = _make_user(db_session, "inviter@example.com")
    invite = _make_invite(db_session, inviter=inviter)

    with pytest.raises(InvitesDisabledError):
        get_valid_pending_invite(db_session, invite.id, _DISABLED_INVITES_CONFIG)


# --- convert_invite ---


def test_convert_invite_transitions_state_no_quota_change(db_session: Session) -> None:
    inviter = _make_user(db_session, "inviter@example.com", quota=4)
    invite = _make_invite(db_session, inviter=inviter)

    convert_invite(db_session, invite.id)

    assert invite.state == InviteState.CONVERTED.value
    assert inviter.invite_quota_remaining == 4


# --- void_invite ---


def test_void_invite_refunds_when_quota_consumed(db_session: Session) -> None:
    inviter = _make_user(db_session, "inviter@example.com", quota=4)
    invite = _make_invite(db_session, inviter=inviter, quota_consumed=True)

    void_invite(db_session, inviter, invite.id)

    assert invite.state == InviteState.VOID.value
    assert inviter.invite_quota_remaining == 5


def test_void_invite_does_not_refund_when_not_quota_consumed(
    db_session: Session,
) -> None:
    inviter = _make_user(db_session, "inviter@example.com", quota=4)
    invite = _make_invite(db_session, inviter=inviter, quota_consumed=False)

    void_invite(db_session, inviter, invite.id)

    assert invite.state == InviteState.VOID.value
    assert inviter.invite_quota_remaining == 4


def test_void_invite_raises_for_non_sender(db_session: Session) -> None:
    inviter = _make_user(db_session, "inviter@example.com")
    other = _make_user(db_session, "other@example.com")
    invite = _make_invite(db_session, inviter=inviter)

    with pytest.raises(InvitePermissionError):
        void_invite(db_session, other, invite.id)


@pytest.mark.parametrize("state", [InviteState.VOID, InviteState.CONVERTED])
def test_void_invite_noops_on_already_non_pending(
    db_session: Session, state: InviteState
) -> None:
    inviter = _make_user(db_session, "inviter@example.com", quota=4)
    invite = _make_invite(db_session, inviter=inviter, state=state, quota_consumed=True)

    void_invite(db_session, inviter, invite.id)

    assert invite.state == state.value
    assert inviter.invite_quota_remaining == 4


# --- admin_void_invite ---


def test_admin_void_invite_ignores_sender_identity(db_session: Session) -> None:
    inviter = _make_user(db_session, "inviter@example.com", quota=4)
    invite = _make_invite(db_session, inviter=inviter, quota_consumed=True)

    admin_void_invite(db_session, invite.id)

    assert invite.state == InviteState.VOID.value
    assert inviter.invite_quota_remaining == 5


# --- replenish_quota ---


def test_replenish_quota_adds_not_sets(db_session: Session) -> None:
    user = _make_user(db_session, "user@example.com", quota=2)

    replenish_quota(db_session, user, 3)
    assert user.invite_quota_remaining == 5

    replenish_quota(db_session, user, 3)
    assert user.invite_quota_remaining == 8


# --- on_user_created ---


def test_on_user_created_with_used_invite_converts_and_voids_siblings(
    db_session: Session,
) -> None:
    inviter1 = _make_user(db_session, "inviter1@example.com", quota=4)
    inviter2 = _make_user(db_session, "inviter2@example.com", quota=4)
    used = _make_invite(
        db_session, inviter=inviter1, email="new@example.com", quota_consumed=True
    )
    sibling_same_sender = _make_invite(
        db_session, inviter=inviter1, email="new@example.com", quota_consumed=True
    )
    sibling_other_sender = _make_invite(
        db_session, inviter=inviter2, email="NEW@example.com", quota_consumed=True
    )
    new_user = User(email="new@example.com", firstname="N", lastname="U")
    db_session.add(new_user)
    db_session.flush()

    on_user_created(db_session, new_user, used_invite_id=used.id)

    assert used.state == InviteState.CONVERTED.value
    assert inviter1.invite_quota_remaining == 5  # used: no refund, sibling: +1
    assert sibling_same_sender.state == InviteState.VOID.value
    assert sibling_other_sender.state == InviteState.VOID.value
    assert inviter2.invite_quota_remaining == 5


def test_on_user_created_without_used_invite_voids_all_pending(
    db_session: Session,
) -> None:
    inviter = _make_user(db_session, "inviter@example.com", quota=4)
    pending = _make_invite(
        db_session, inviter=inviter, email="plain@example.com", quota_consumed=True
    )
    new_user = User(email="plain@example.com", firstname="N", lastname="U")
    db_session.add(new_user)
    db_session.flush()

    on_user_created(db_session, new_user)

    assert pending.state == InviteState.VOID.value
    assert inviter.invite_quota_remaining == 5


# --- delete_invite ---


def test_delete_invite_pending_quota_consumed_refunds_and_removes(
    db_session: Session,
) -> None:
    inviter = _make_user(db_session, "inviter@example.com", quota=4)
    invite = _make_invite(db_session, inviter=inviter, quota_consumed=True)
    invite_id = invite.id

    delete_invite(db_session, invite_id)

    assert inviter.invite_quota_remaining == 5
    assert db_session.get(Invite, invite_id) is None


@pytest.mark.parametrize("state", [InviteState.VOID, InviteState.CONVERTED])
def test_delete_invite_non_pending_no_quota_change(
    db_session: Session, state: InviteState
) -> None:
    inviter = _make_user(db_session, "inviter@example.com", quota=4)
    invite = _make_invite(db_session, inviter=inviter, state=state, quota_consumed=True)
    invite_id = invite.id

    delete_invite(db_session, invite_id)

    assert inviter.invite_quota_remaining == 4
    assert db_session.get(Invite, invite_id) is None


def test_delete_invite_unknown_id_is_noop(db_session: Session) -> None:
    delete_invite(db_session, uuid.uuid4())
