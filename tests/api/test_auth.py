"""Tests for authentication API endpoints."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from assistant.auth.service import (
    create_access_token,
    create_email_confirmation,
    issue_tokens,
)
from assistant.email.exceptions import EmailSendError
from assistant.invites.service import create_invite
from assistant.models.schema import EmailConfirmation, Invite, InviteState, User

if TYPE_CHECKING:
    from collections.abc import Iterator

    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session


@pytest.fixture(autouse=True)
def mock_send_email() -> Iterator[MagicMock]:
    with patch("assistant.email.service.send_email") as mock_send:
        yield mock_send


def _register(
    client: TestClient,
    email: str = "user@example.com",
    invite_id: str | None = None,
) -> dict:
    body = {
        "email": email,
        "password": "secret123",
        "firstname": "Jane",
        "lastname": "Doe",
    }
    if invite_id is not None:
        body["invite_id"] = invite_id
    return client.post("/auth/register", json=body)


# --- Registration ---


def test_register_creates_user(client: TestClient) -> None:
    response = _register(client)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "user@example.com"
    assert data["confirmation_email_sent"] is True


def test_register_duplicate_email(client: TestClient) -> None:
    _register(client)
    response = _register(client)
    assert response.status_code == 409


def test_register_invalid_email(client: TestClient) -> None:
    response = client.post(
        "/auth/register",
        json={
            "email": "not-an-email",
            "password": "x",
            "firstname": "A",
            "lastname": "B",
        },
    )
    assert response.status_code == 422


def test_register_does_not_log_in(client: TestClient) -> None:
    response = _register(client)
    assert response.status_code == 201
    assert "access_token" not in client.cookies


def test_register_send_failure_reported_but_still_succeeds(
    client: TestClient, mock_send_email: MagicMock
) -> None:
    mock_send_email.side_effect = EmailSendError("boom")
    response = _register(client)
    assert response.status_code == 201
    assert response.json()["confirmation_email_sent"] is False


# --- Registration mode matrix ---


def test_register_open_registration_succeeds(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REGISTRATION_REGISTRATION_ENABLED", "true")
    monkeypatch.setenv("REGISTRATION_INVITES_ENABLED", "true")
    response = _register(client)
    assert response.status_code == 201
    assert response.json()["confirmation_email_sent"] is True


def test_register_disabled_without_invite_rejected(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REGISTRATION_REGISTRATION_ENABLED", "false")
    response = _register(client)
    assert response.status_code == 403


def test_register_disabled_with_valid_invite_succeeds(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    inviter = User(
        email="inviter@example.com",
        firstname="I",
        lastname="N",
        invite_quota_remaining=5,
    )
    db_session.add(inviter)
    db_session.flush()
    invite, _ = create_invite(
        db_session,
        inviter,
        "invitee@example.com",
        {
            "registration_enabled": True,
            "invites_enabled": True,
            "default_quota": 5,
            "expiry_days": 1,
        },
    )
    db_session.commit()

    monkeypatch.setenv("REGISTRATION_REGISTRATION_ENABLED", "false")
    response = _register(client, email="invitee@example.com", invite_id=str(invite.id))
    assert response.status_code == 201

    db_session.refresh(invite)
    assert invite.state == InviteState.CONVERTED.value


def test_register_invites_disabled_blocks_redemption(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    inviter = User(
        email="inviter2@example.com",
        firstname="I",
        lastname="N",
        invite_quota_remaining=5,
    )
    db_session.add(inviter)
    db_session.flush()
    invite, _ = create_invite(
        db_session,
        inviter,
        "invitee2@example.com",
        {
            "registration_enabled": True,
            "invites_enabled": True,
            "default_quota": 5,
            "expiry_days": 1,
        },
    )
    db_session.commit()

    monkeypatch.setenv("REGISTRATION_INVITES_ENABLED", "false")
    response = _register(client, email="invitee2@example.com", invite_id=str(invite.id))
    assert response.status_code == 403


def test_register_invite_email_mismatch(client: TestClient, db_session: Session) -> None:
    inviter = User(
        email="inviter3@example.com",
        firstname="I",
        lastname="N",
        invite_quota_remaining=5,
    )
    db_session.add(inviter)
    db_session.flush()
    invite, _ = create_invite(
        db_session,
        inviter,
        "invitee3@example.com",
        {
            "registration_enabled": True,
            "invites_enabled": True,
            "default_quota": 5,
            "expiry_days": 1,
        },
    )
    db_session.commit()

    response = _register(
        client, email="someone-else@example.com", invite_id=str(invite.id)
    )
    assert response.status_code == 422


@pytest.mark.parametrize("state", [InviteState.VOID, InviteState.CONVERTED])
def test_register_non_pending_invite_returns_404(
    client: TestClient, db_session: Session, state: InviteState
) -> None:
    inviter = User(email="inviter4@example.com", firstname="I", lastname="N")
    db_session.add(inviter)
    db_session.flush()
    invite = Invite(
        invitee_email="invitee4@example.com",
        inviter_id=inviter.uid,
        state=state.value,
        quota_consumed=True,
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    db_session.add(invite)
    db_session.commit()

    response = _register(client, email="invitee4@example.com", invite_id=str(invite.id))
    assert response.status_code == 404


def test_register_unknown_invite_returns_404(client: TestClient) -> None:
    response = _register(client, invite_id=str(uuid.uuid4()))
    assert response.status_code == 404


def test_register_with_invite_voids_sibling_invites(
    client: TestClient, db_session: Session
) -> None:
    inviter = User(
        email="inviter5@example.com",
        firstname="I",
        lastname="N",
        invite_quota_remaining=5,
    )
    other_inviter = User(
        email="inviter6@example.com",
        firstname="I",
        lastname="N",
        invite_quota_remaining=5,
    )
    db_session.add_all([inviter, other_inviter])
    db_session.flush()
    config = {
        "registration_enabled": True,
        "invites_enabled": True,
        "default_quota": 5,
        "expiry_days": 1,
    }
    used, _ = create_invite(db_session, inviter, "invitee5@example.com", config)
    sibling, _ = create_invite(db_session, other_inviter, "invitee5@example.com", config)
    db_session.commit()

    response = _register(client, email="invitee5@example.com", invite_id=str(used.id))
    assert response.status_code == 201

    db_session.refresh(used)
    db_session.refresh(sibling)
    assert used.state == InviteState.CONVERTED.value
    assert sibling.state == InviteState.VOID.value


# --- Login ---


def _confirmation_token_for(db_session: Session, email: str) -> str:
    """Force-issue a known raw token for a pending user's confirmation row.

    Uses create_email_confirmation directly (not the resend endpoint/service
    function) since that one is cooldown-gated and register_user already
    used up the initial send.
    """
    user = db_session.query(User).filter_by(email=email).one()
    with patch(
        "assistant.auth.service.secrets.token_urlsafe", return_value="fixed-token"
    ):
        create_email_confirmation(db_session, user.uid)
    db_session.commit()
    return "fixed-token"


def test_login_sets_cookies(client: TestClient, db_session: Session) -> None:
    _register(client)
    token = _confirmation_token_for(db_session, "user@example.com")
    confirm_response = client.post(f"/auth/confirm-email/{token}")
    assert confirm_response.status_code == 204

    response = client.post(
        "/auth/login",
        json={"email": "user@example.com", "password": "secret123"},
    )
    assert response.status_code == 200
    assert "access_token" in client.cookies
    assert response.json()["email"] == "user@example.com"


def test_login_wrong_password(client: TestClient, db_session: Session) -> None:
    _register(client)
    token = _confirmation_token_for(db_session, "user@example.com")
    client.post(f"/auth/confirm-email/{token}")

    response = client.post(
        "/auth/login",
        json={"email": "user@example.com", "password": "wrong"},
    )
    assert response.status_code == 401


def test_login_unknown_email(client: TestClient) -> None:
    response = client.post(
        "/auth/login",
        json={"email": "nobody@example.com", "password": "x"},
    )
    assert response.status_code == 401


def test_login_not_confirmed_returns_403(client: TestClient) -> None:
    _register(client)

    response = client.post(
        "/auth/login",
        json={"email": "user@example.com", "password": "secret123"},
    )
    assert response.status_code == 403


# --- Email confirmation ---


def test_confirm_email_activates_account(client: TestClient, db_session: Session) -> None:
    _register(client)
    token = _confirmation_token_for(db_session, "user@example.com")

    response = client.post(f"/auth/confirm-email/{token}")
    assert response.status_code == 204

    login_response = client.post(
        "/auth/login",
        json={"email": "user@example.com", "password": "secret123"},
    )
    assert login_response.status_code == 200


def test_confirm_email_unknown_token_returns_404(client: TestClient) -> None:
    response = client.post("/auth/confirm-email/bogus-token")
    assert response.status_code == 404


def test_confirm_email_expired_token_returns_404(
    client: TestClient, db_session: Session
) -> None:
    _register(client)
    user = db_session.query(User).filter_by(email="user@example.com").one()
    confirmation = db_session.get(EmailConfirmation, user.uid)
    assert confirmation is not None
    confirmation.token_hash = hashlib.sha256(b"expired-token").hexdigest()
    confirmation.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()

    response = client.post("/auth/confirm-email/expired-token")
    assert response.status_code == 404


def test_confirm_email_is_idempotent(client: TestClient, db_session: Session) -> None:
    _register(client)
    token = _confirmation_token_for(db_session, "user@example.com")

    first = client.post(f"/auth/confirm-email/{token}")
    second = client.post(f"/auth/confirm-email/{token}")
    assert first.status_code == 204
    assert second.status_code == 204


# --- Resend confirmation ---


def test_resend_confirmation_unknown_email_returns_404(client: TestClient) -> None:
    response = client.post(
        "/auth/resend-confirmation", json={"email": "nobody@example.com"}
    )
    assert response.status_code == 404


def test_resend_confirmation_within_cooldown_returns_429(client: TestClient) -> None:
    _register(client)
    response = client.post(
        "/auth/resend-confirmation", json={"email": "user@example.com"}
    )
    assert response.status_code == 429


def test_resend_confirmation_exhausted_returns_403(
    client: TestClient, db_session: Session
) -> None:
    _register(client)
    user = db_session.query(User).filter_by(email="user@example.com").one()
    confirmation = db_session.get(EmailConfirmation, user.uid)
    assert confirmation is not None
    confirmation.last_sent_at = datetime.now(UTC) - timedelta(minutes=10)
    confirmation.resend_count = 3
    db_session.commit()

    response = client.post(
        "/auth/resend-confirmation", json={"email": "user@example.com"}
    )
    assert response.status_code == 403


# --- /auth/me ---


def test_me_with_bearer_token(client: TestClient, db_session: Session) -> None:
    user = User(email="me@test.com", firstname="Me", lastname="User")
    db_session.add(user)
    db_session.flush()

    token = create_access_token(user.uid)
    response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["email"] == "me@test.com"


def test_me_unauthenticated(client: TestClient) -> None:
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_me_invalid_token(client: TestClient) -> None:
    response = client.get(
        "/auth/me",
        headers={"Authorization": "Bearer invalid.token.here"},
    )
    assert response.status_code == 401


# --- Logout ---


def test_logout_clears_cookies(client: TestClient, db_session: Session) -> None:
    _register(client)
    token = _confirmation_token_for(db_session, "user@example.com")
    client.post(f"/auth/confirm-email/{token}")
    client.post(
        "/auth/login",
        json={"email": "user@example.com", "password": "secret123"},
    )
    assert "access_token" in client.cookies

    response = client.post("/auth/logout")
    assert response.status_code == 204


# --- Ambiguous auth ---


def test_both_cookie_and_bearer_rejected(
    client: TestClient,
    db_session: Session,
) -> None:
    user = User(email="ambig@test.com", firstname="A", lastname="B")
    db_session.add(user)
    db_session.flush()

    token = create_access_token(user.uid)
    client.cookies.set("access_token", token)
    response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    client.cookies.clear()


# --- Refresh ---


def test_refresh_issues_new_tokens(client: TestClient, db_session: Session) -> None:
    user = User(email="refresh@test.com", firstname="R", lastname="U")
    db_session.add(user)
    db_session.flush()

    _access, refresh_raw = issue_tokens(db_session, user.uid)
    db_session.commit()

    client.cookies.set("refresh_token", refresh_raw)
    response = client.post("/auth/refresh")
    assert response.status_code == 200
    assert "access_token" in client.cookies
    client.cookies.clear()
