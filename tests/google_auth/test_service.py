"""Tests for the google_auth service module."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from assistant.google_auth.exceptions import (
    GoogleAccountCollisionError,
    GoogleEmailNotVerifiedError,
)
from assistant.google_auth.oauth import GoogleIdTokenClaims
from assistant.google_auth.service import handle_google_callback
from assistant.invites.exceptions import (
    InviteEmailMismatchError,
    RegistrationDisabledError,
)
from assistant.invites.service import create_invite
from assistant.models.schema import Credential, InviteState, User

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_REGISTRATION_CONFIG = {
    "registration_enabled": True,
    "invites_enabled": True,
    "default_quota": 5,
    "expiry_days": 1,
}


def _claims(**overrides: object) -> GoogleIdTokenClaims:
    defaults: dict[str, object] = {
        "sub": "google-sub-123",
        "email": "user@example.com",
        "email_verified": True,
        "given_name": "Ada",
        "family_name": "Lovelace",
    }
    defaults.update(overrides)
    return GoogleIdTokenClaims(**defaults)  # type: ignore[arg-type]


# --- Email verification ---


def test_unverified_email_raises_and_creates_no_user(db_session: Session) -> None:
    with pytest.raises(GoogleEmailNotVerifiedError):
        handle_google_callback(
            db_session, claims=_claims(email_verified=False), invite_id=None
        )

    assert db_session.query(User).filter_by(email="user@example.com").first() is None


# --- First-time sign-in ---


def test_first_time_signin_creates_user_and_google_credential(
    db_session: Session,
) -> None:
    user = handle_google_callback(db_session, claims=_claims(), invite_id=None)

    assert user.email == "user@example.com"
    assert user.firstname == "Ada"
    assert user.lastname == "Lovelace"

    credential = db_session.query(Credential).filter_by(user_id=user.uid).one()
    assert credential.provider == "google"
    assert credential.provider_subject == "google-sub-123"


def test_missing_given_name_maps_to_empty_string(db_session: Session) -> None:
    user = handle_google_callback(
        db_session, claims=_claims(given_name=None), invite_id=None
    )
    assert user.firstname == ""


# --- Returning user ---


def test_second_callback_same_sub_returns_same_user_no_new_row(
    db_session: Session,
) -> None:
    first = handle_google_callback(db_session, claims=_claims(), invite_id=None)
    second = handle_google_callback(db_session, claims=_claims(), invite_id=None)

    assert first.uid == second.uid
    assert db_session.query(User).filter_by(email="user@example.com").count() == 1


# --- Collision ---


def test_email_with_existing_password_credential_collides(
    db_session: Session,
) -> None:
    existing = User(email="user@example.com", firstname="Existing", lastname="User")
    db_session.add(existing)
    db_session.flush()
    credential = Credential(
        user_id=existing.uid, provider="password", credential_hash="hash"
    )
    db_session.add(credential)
    db_session.flush()

    with pytest.raises(GoogleAccountCollisionError):
        handle_google_callback(db_session, claims=_claims(), invite_id=None)

    assert db_session.query(Credential).filter_by(provider="google").first() is None


# --- Registration gating ---


def test_registration_disabled_without_invite_propagates(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REGISTRATION_REGISTRATION_ENABLED", "false")

    with pytest.raises(RegistrationDisabledError):
        handle_google_callback(db_session, claims=_claims(), invite_id=None)


def test_valid_invite_matching_email_succeeds_and_converts(
    db_session: Session,
) -> None:
    inviter = User(
        email="inviter@example.com",
        firstname="I",
        lastname="N",
        invite_quota_remaining=5,
    )
    db_session.add(inviter)
    db_session.flush()
    invite, _email_sent = create_invite(
        db_session, inviter, "user@example.com", _REGISTRATION_CONFIG
    )

    user = handle_google_callback(db_session, claims=_claims(), invite_id=invite.id)

    assert user.email == "user@example.com"
    db_session.refresh(invite)
    assert invite.state == InviteState.CONVERTED.value


def test_invite_email_mismatch_raises(db_session: Session) -> None:
    inviter = User(
        email="inviter2@example.com",
        firstname="I",
        lastname="N",
        invite_quota_remaining=5,
    )
    db_session.add(inviter)
    db_session.flush()
    invite, _email_sent = create_invite(
        db_session, inviter, "someone-else@example.com", _REGISTRATION_CONFIG
    )

    with pytest.raises(InviteEmailMismatchError):
        handle_google_callback(db_session, claims=_claims(), invite_id=invite.id)
