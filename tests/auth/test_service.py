"""Tests for the auth service's email-confirmation lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from assistant.auth.exceptions import (
    AccountNotConfirmedError,
    AuthError,
    ConfirmationCooldownError,
    ConfirmationLimitExceededError,
    ConfirmationNotFoundError,
    ConfirmationTokenInvalidError,
)
from assistant.auth.service import (
    CONFIRMATION_RESEND_COOLDOWN,
    MAX_CONFIRMATION_SENDS,
    _hash_token,
    _ph,
    _reap_expired_pending_registration,
    authenticate_user,
    confirm_email,
    create_email_confirmation,
    register_user,
    resend_confirmation,
)
from assistant.email.exceptions import EmailSendError
from assistant.models.schema import Credential, EmailConfirmation, User, UserStatus

_REGISTRATION_KWARGS = {
    "email": "new@example.com",
    "password": "secret123",
    "firstname": "New",
    "lastname": "User",
}


def _make_pending_user(session: Session, email: str = "pending@example.com") -> User:
    user = User(email=email, firstname="P", lastname="U", status=UserStatus.PENDING.value)
    session.add(user)
    session.flush()
    credential = Credential(
        user_id=user.uid, provider="password", credential_hash=_ph.hash("secret123")
    )
    session.add(credential)
    session.flush()
    return user


def _make_active_user(session: Session, email: str = "active@example.com") -> User:
    user = User(email=email, firstname="A", lastname="U", status=UserStatus.ACTIVE.value)
    session.add(user)
    session.flush()
    credential = Credential(
        user_id=user.uid, provider="password", credential_hash=_ph.hash("secret123")
    )
    session.add(credential)
    session.flush()
    return user


def _make_confirmation(  # noqa: PLR0913
    session: Session,
    user: User,
    *,
    token: str = "raw-token",
    expires_at: datetime | None = None,
    last_sent_at: datetime | None = None,
    resend_count: int = 1,
) -> EmailConfirmation:
    confirmation = EmailConfirmation(
        user_id=user.uid,
        token_hash=_hash_token(token),
        expires_at=expires_at or (datetime.now(UTC) + timedelta(hours=24)),
        last_sent_at=last_sent_at or datetime.now(UTC),
        resend_count=resend_count,
    )
    session.add(confirmation)
    session.flush()
    return confirmation


# --- create_email_confirmation ---


def test_create_email_confirmation_creates_row_with_resend_count_1(
    db_session: Session,
) -> None:
    user = _make_pending_user(db_session)

    create_email_confirmation(db_session, user.uid)

    confirmation = db_session.get(EmailConfirmation, user.uid)
    assert confirmation is not None
    assert confirmation.resend_count == 1


def test_create_email_confirmation_overwrites_existing_row(db_session: Session) -> None:
    user = _make_pending_user(db_session)

    first_token = create_email_confirmation(db_session, user.uid)
    second_token = create_email_confirmation(db_session, user.uid)

    assert first_token != second_token
    confirmation = db_session.get(EmailConfirmation, user.uid)
    assert confirmation is not None
    assert confirmation.resend_count == 2
    assert confirmation.token_hash == _hash_token(second_token)


# --- confirm_email ---


def test_confirm_email_activates_pending_user(db_session: Session) -> None:
    user = _make_pending_user(db_session)
    _make_confirmation(db_session, user, token="tok")

    confirmed = confirm_email(db_session, "tok")

    assert confirmed.status == UserStatus.ACTIVE.value


def test_confirm_email_raises_for_unknown_token(db_session: Session) -> None:
    with pytest.raises(ConfirmationTokenInvalidError):
        confirm_email(db_session, "does-not-exist")


def test_confirm_email_raises_for_expired_token(db_session: Session) -> None:
    user = _make_pending_user(db_session)
    _make_confirmation(
        db_session,
        user,
        token="tok",
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )

    with pytest.raises(ConfirmationTokenInvalidError):
        confirm_email(db_session, "tok")


def test_confirm_email_idempotent_for_already_active_user(db_session: Session) -> None:
    user = _make_active_user(db_session)
    _make_confirmation(db_session, user, token="tok")

    confirmed = confirm_email(db_session, "tok")

    assert confirmed.status == UserStatus.ACTIVE.value


# --- resend_confirmation ---


def test_resend_confirmation_raises_for_unknown_email(db_session: Session) -> None:
    with pytest.raises(ConfirmationNotFoundError):
        resend_confirmation(db_session, "nobody@example.com")


def test_resend_confirmation_raises_for_already_active_user(db_session: Session) -> None:
    user = _make_active_user(db_session)
    _make_confirmation(db_session, user)

    with pytest.raises(ConfirmationNotFoundError):
        resend_confirmation(db_session, user.email)


def test_resend_confirmation_raises_cooldown(db_session: Session) -> None:
    user = _make_pending_user(db_session)
    _make_confirmation(db_session, user, last_sent_at=datetime.now(UTC))

    with (
        patch("assistant.email.service.send_email"),
        pytest.raises(ConfirmationCooldownError),
    ):
        resend_confirmation(db_session, user.email)


def test_resend_confirmation_succeeds_after_cooldown(db_session: Session) -> None:
    user = _make_pending_user(db_session)
    _make_confirmation(
        db_session,
        user,
        last_sent_at=(
            datetime.now(UTC) - CONFIRMATION_RESEND_COOLDOWN - timedelta(seconds=1)
        ),
        resend_count=1,
    )

    with patch("assistant.email.service.send_email") as mock_send:
        result = resend_confirmation(db_session, user.email)

    assert result is True
    mock_send.assert_called_once()
    confirmation = db_session.get(EmailConfirmation, user.uid)
    assert confirmation is not None
    assert confirmation.resend_count == 2


def test_resend_confirmation_raises_limit_exceeded(db_session: Session) -> None:
    user = _make_pending_user(db_session)
    _make_confirmation(
        db_session,
        user,
        last_sent_at=(
            datetime.now(UTC) - CONFIRMATION_RESEND_COOLDOWN - timedelta(seconds=1)
        ),
        resend_count=MAX_CONFIRMATION_SENDS,
    )

    with pytest.raises(ConfirmationLimitExceededError):
        resend_confirmation(db_session, user.email)


# --- _reap_expired_pending_registration ---


def test_reap_deletes_expired_pending_registration(db_session: Session) -> None:
    user = _make_pending_user(db_session, "stale@example.com")
    _make_confirmation(
        db_session,
        user,
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    user_id = user.uid

    _reap_expired_pending_registration(db_session, "stale@example.com")

    assert db_session.get(User, user_id) is None
    assert db_session.get(EmailConfirmation, user_id) is None


def test_reap_leaves_unexpired_pending_registration(db_session: Session) -> None:
    user = _make_pending_user(db_session, "fresh@example.com")
    _make_confirmation(db_session, user)
    user_id = user.uid

    _reap_expired_pending_registration(db_session, "fresh@example.com")

    assert db_session.get(User, user_id) is not None


def test_reap_leaves_active_user(db_session: Session) -> None:
    user = _make_active_user(db_session, "keep@example.com")
    user_id = user.uid

    _reap_expired_pending_registration(db_session, "keep@example.com")

    assert db_session.get(User, user_id) is not None


def test_reap_noop_for_unknown_email(db_session: Session) -> None:
    _reap_expired_pending_registration(db_session, "nobody@example.com")


# --- register_user ---


def test_register_user_sets_pending_and_sends_confirmation(db_session: Session) -> None:
    with patch("assistant.email.service.send_email") as mock_send:
        user, email_sent = register_user(db_session, **_REGISTRATION_KWARGS)

    assert user.status == UserStatus.PENDING.value
    assert email_sent is True
    mock_send.assert_called_once()
    confirmation = db_session.get(EmailConfirmation, user.uid)
    assert confirmation is not None


def test_register_user_returns_email_sent_false_on_send_failure(
    db_session: Session,
) -> None:
    with patch("assistant.email.service.send_email", side_effect=EmailSendError("boom")):
        user, email_sent = register_user(db_session, **_REGISTRATION_KWARGS)

    assert user.status == UserStatus.PENDING.value
    assert email_sent is False
    assert db_session.get(User, user.uid) is not None


# --- authenticate_user ---


def test_authenticate_user_raises_account_not_confirmed_for_pending_user(
    db_session: Session,
) -> None:
    user = _make_pending_user(db_session)

    with pytest.raises(AccountNotConfirmedError):
        authenticate_user(db_session, email=user.email, password="secret123")


def test_authenticate_user_raises_auth_error_for_pending_user_wrong_password(
    db_session: Session,
) -> None:
    user = _make_pending_user(db_session)

    with pytest.raises(AuthError):
        authenticate_user(db_session, email=user.email, password="wrong")


def test_authenticate_user_succeeds_for_active_user(db_session: Session) -> None:
    user = _make_active_user(db_session)

    authenticated = authenticate_user(db_session, email=user.email, password="secret123")

    assert authenticated.uid == user.uid
