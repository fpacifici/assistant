"""Tests for the manage-invites admin CLI."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from assistant.cli.manage_invites import main
from assistant.email.exceptions import EmailSendError
from assistant.models.schema import Invite, InviteState, User


@pytest.fixture(autouse=True)
def mock_send_invite_email() -> Iterator[MagicMock]:
    with patch("assistant.email.service.send_email") as mock_send:
        yield mock_send


def _make_user(session: Session, email: str, *, quota: int = 5) -> User:
    user = User(email=email, firstname="A", lastname="B", invite_quota_remaining=quota)
    session.add(user)
    session.flush()
    return user


def _make_pending_invite(session: Session, sender: User, email: str) -> Invite:
    invite = Invite(
        invitee_email=email,
        inviter_id=sender.uid,
        state=InviteState.PENDING.value,
        quota_consumed=True,
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    session.add(invite)
    session.commit()
    return invite


def _run(db_session: Session, argv: list[str]) -> None:
    # The CLI's `with session_factory() as session:` closes the session on
    # exit (matching real sessionmaker-per-invocation usage) — this reuses
    # the shared test db_session as that "fresh" session, so callers must
    # re-fetch rows afterward rather than refresh() stale Python objects.
    with (
        patch(
            "assistant.cli.manage_invites.get_session_factory",
            return_value=lambda: db_session,
        ),
        patch("sys.argv", ["manage_invites", *argv]),
    ):
        main()


# --- create ---


def test_create_attributes_invite_and_bypasses_quota(db_session: Session) -> None:
    sender = _make_user(db_session, "sender@example.com", quota=5)
    sender_uid = sender.uid
    db_session.commit()

    _run(db_session, ["create", "--as", "sender@example.com", "--to", "new@example.com"])

    invite = db_session.query(Invite).filter_by(invitee_email="new@example.com").one()
    assert invite.inviter_id == sender_uid
    assert invite.quota_consumed is False
    assert invite.state == InviteState.PENDING.value
    refreshed_sender = db_session.get(User, sender_uid)
    assert refreshed_sender is not None
    assert refreshed_sender.invite_quota_remaining == 5


def test_create_reports_email_sent_status(
    db_session: Session,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _make_user(db_session, "sender@example.com", quota=5)
    db_session.commit()

    _run(db_session, ["create", "--as", "sender@example.com", "--to", "new@example.com"])

    assert "email sent" in capsys.readouterr().out


def test_create_reports_email_send_failure(
    db_session: Session,
    capsys: pytest.CaptureFixture[str],
    mock_send_invite_email: MagicMock,
) -> None:
    mock_send_invite_email.side_effect = EmailSendError("boom")
    _make_user(db_session, "sender2@example.com", quota=5)
    db_session.commit()

    _run(
        db_session,
        ["create", "--as", "sender2@example.com", "--to", "new2@example.com"],
    )

    assert "EMAIL SEND FAILED" in capsys.readouterr().out


# --- void ---


def test_void_force_voids_regardless_of_sender(db_session: Session) -> None:
    sender = _make_user(db_session, "sender@example.com", quota=5)
    sender_uid = sender.uid
    invite = _make_pending_invite(db_session, sender, "a@example.com")
    invite_id = invite.id

    _run(db_session, ["void", "--id", str(invite_id)])

    refreshed_invite = db_session.get(Invite, invite_id)
    assert refreshed_invite is not None
    assert refreshed_invite.state == InviteState.VOID.value
    refreshed_sender = db_session.get(User, sender_uid)
    assert refreshed_sender is not None
    assert refreshed_sender.invite_quota_remaining == 6


# --- replenish ---


def test_replenish_adds_cumulatively(db_session: Session) -> None:
    user = _make_user(db_session, "user@example.com", quota=2)
    user_uid = user.uid
    db_session.commit()

    _run(db_session, ["replenish", "--email", "user@example.com", "--amount", "3"])
    refreshed = db_session.get(User, user_uid)
    assert refreshed is not None
    assert refreshed.invite_quota_remaining == 5

    _run(db_session, ["replenish", "--email", "user@example.com", "--amount", "3"])
    refreshed = db_session.get(User, user_uid)
    assert refreshed is not None
    assert refreshed.invite_quota_remaining == 8


# --- delete ---


def test_delete_with_yes_removes_and_refunds(db_session: Session) -> None:
    sender = _make_user(db_session, "sender@example.com", quota=4)
    sender_uid = sender.uid
    invite = _make_pending_invite(db_session, sender, "a@example.com")
    invite_id = invite.id

    _run(db_session, ["delete", "--id", str(invite_id), "--yes"])

    assert db_session.get(Invite, invite_id) is None
    refreshed_sender = db_session.get(User, sender_uid)
    assert refreshed_sender is not None
    assert refreshed_sender.invite_quota_remaining == 5


def test_delete_without_yes_prompts_and_declines(db_session: Session) -> None:
    sender = _make_user(db_session, "sender@example.com", quota=4)
    sender_uid = sender.uid
    invite = _make_pending_invite(db_session, sender, "a@example.com")
    invite_id = invite.id

    with patch("builtins.input", return_value="n"):
        _run(db_session, ["delete", "--id", str(invite_id)])

    assert db_session.get(Invite, invite_id) is not None
    refreshed_sender = db_session.get(User, sender_uid)
    assert refreshed_sender is not None
    assert refreshed_sender.invite_quota_remaining == 4
