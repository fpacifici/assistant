"""Tests for swapping a user's credential between password and Google."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from assistant.auth.credentials import (
    get_auth_provider,
    google_swap_requires_password,
    swap_to_google,
    swap_to_password,
)
from assistant.auth.exceptions import AuthError, CredentialSwapError
from assistant.auth.service import hash_password, verify_password
from assistant.google_auth.exceptions import GoogleAccountCollisionError
from assistant.models.schema import (
    Credential,
    EmailConfirmation,
    RefreshToken,
    User,
    UserStatus,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.orm import Session


@pytest.fixture(autouse=True)
def mock_send_email() -> Iterator[MagicMock]:
    """Every swap sends a notification email; keep it off the network."""
    with patch("assistant.email.service.send_email") as mock_send:
        yield mock_send


def _make_user(
    session: Session,
    *,
    email: str = "user@example.com",
    provider: str = "password",
    status: str = UserStatus.ACTIVE.value,
) -> User:
    user = User(email=email, firstname="U", lastname="Ser", status=status)
    session.add(user)
    session.flush()
    if provider == "password":
        credential = Credential(
            user_id=user.uid,
            provider="password",
            credential_hash=hash_password("secret123"),
        )
    else:
        credential = Credential(
            user_id=user.uid, provider="google", provider_subject=f"sub-{email}"
        )
    session.add(credential)
    session.flush()
    return user


def _add_refresh_token(session: Session, user: User) -> None:
    session.add(
        RefreshToken(
            user_id=user.uid,
            family_id=uuid.uuid4(),
            token_hash=uuid.uuid4().hex,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
    )
    session.flush()


def _credentials(session: Session, user: User) -> list[Credential]:
    return session.query(Credential).filter_by(user_id=user.uid).all()


# --- get_auth_provider ---


def test_get_auth_provider(db_session: Session) -> None:
    password_user = _make_user(db_session, email="p@example.com")
    google_user = _make_user(db_session, email="g@example.com", provider="google")

    assert get_auth_provider(db_session, password_user.uid) == "password"
    assert get_auth_provider(db_session, google_user.uid) == "google"


# --- swap_to_google ---


def test_swap_to_google_replaces_password_credential(db_session: Session) -> None:
    user = _make_user(db_session)
    _add_refresh_token(db_session, user)

    swap_to_google(
        db_session,
        user_id=user.uid,
        email="user@example.com",
        google_sub="google-sub",
        password="secret123",
    )

    [credential] = _credentials(db_session, user)
    assert credential.provider == "google"
    assert credential.provider_subject == "google-sub"
    assert db_session.query(RefreshToken).filter_by(user_id=user.uid).count() == 0


def test_swap_to_google_wrong_password_changes_nothing(db_session: Session) -> None:
    user = _make_user(db_session)

    with pytest.raises(AuthError):
        swap_to_google(
            db_session,
            user_id=user.uid,
            email="user@example.com",
            google_sub="google-sub",
            password="wrong",
        )

    [credential] = _credentials(db_session, user)
    assert credential.provider == "password"


def test_swap_to_google_without_password_rejected(db_session: Session) -> None:
    user = _make_user(db_session)

    assert google_swap_requires_password(db_session, user.uid)
    with pytest.raises(AuthError):
        swap_to_google(
            db_session,
            user_id=user.uid,
            email="user@example.com",
            google_sub="google-sub",
            password=None,
        )


def test_swap_to_google_claims_pending_user_without_password(
    db_session: Session,
) -> None:
    # An unconfirmed registration never proved it owns the email; Google
    # did, so the password (which the email's owner may not know) is moot.
    user = _make_user(db_session, status=UserStatus.PENDING.value)
    db_session.add(
        EmailConfirmation(
            user_id=user.uid,
            token_hash="hash",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            last_sent_at=datetime.now(UTC),
            resend_count=1,
        )
    )
    db_session.flush()

    assert not google_swap_requires_password(db_session, user.uid)
    swap_to_google(
        db_session,
        user_id=user.uid,
        email="user@example.com",
        google_sub="google-sub",
        password=None,
    )

    assert user.status == UserStatus.ACTIVE.value
    assert db_session.get(EmailConfirmation, user.uid) is None
    [credential] = _credentials(db_session, user)
    assert credential.provider == "google"


def test_swap_to_google_notifies_owner(
    db_session: Session, mock_send_email: MagicMock
) -> None:
    user = _make_user(db_session)

    swap_to_google(
        db_session,
        user_id=user.uid,
        email="user@example.com",
        google_sub="google-sub",
        password="secret123",
    )

    [email] = [c.args[0] for c in mock_send_email.call_args_list]
    assert email.recipient == "user@example.com"
    assert email.values["method"] == "Google"


def test_swap_to_google_rejects_email_mismatch(db_session: Session) -> None:
    user = _make_user(db_session)

    with pytest.raises(CredentialSwapError):
        swap_to_google(
            db_session,
            user_id=user.uid,
            email="other@example.com",
            google_sub="google-sub",
            password="secret123",
        )


def test_swap_to_google_rejects_google_user(db_session: Session) -> None:
    user = _make_user(db_session, provider="google")

    with pytest.raises(CredentialSwapError):
        swap_to_google(
            db_session,
            user_id=user.uid,
            email="user@example.com",
            google_sub="another-sub",
            password="secret123",
        )


def test_swap_to_google_rejects_sub_owned_by_other_user(db_session: Session) -> None:
    user = _make_user(db_session)
    other = _make_user(db_session, email="other@example.com", provider="google")
    [other_credential] = _credentials(db_session, other)

    with pytest.raises(GoogleAccountCollisionError):
        swap_to_google(
            db_session,
            user_id=user.uid,
            email="user@example.com",
            google_sub=other_credential.provider_subject or "",
            password="secret123",
        )


# --- swap_to_password ---


def test_swap_to_password_replaces_google_credential(db_session: Session) -> None:
    user = _make_user(db_session, provider="google")
    _add_refresh_token(db_session, user)

    swap_to_password(db_session, user_id=user.uid, password="newsecret1")

    [credential] = _credentials(db_session, user)
    assert credential.provider == "password"
    assert credential.credential_hash is not None
    assert verify_password(credential.credential_hash, "newsecret1")
    assert db_session.query(RefreshToken).filter_by(user_id=user.uid).count() == 0


def test_swap_to_password_rejects_password_user(
    db_session: Session, mock_send_email: MagicMock
) -> None:
    user = _make_user(db_session)

    with pytest.raises(CredentialSwapError):
        swap_to_password(db_session, user_id=user.uid, password="newsecret1")
    mock_send_email.assert_not_called()


def test_swap_to_password_notifies_owner(
    db_session: Session, mock_send_email: MagicMock
) -> None:
    user = _make_user(db_session, email="g@example.com", provider="google")

    swap_to_password(db_session, user_id=user.uid, password="newsecret1")

    [email] = [c.args[0] for c in mock_send_email.call_args_list]
    assert email.recipient == "g@example.com"
    assert email.values["method"] == "your email and a password"
