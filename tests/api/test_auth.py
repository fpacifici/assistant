"""Tests for authentication API endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from assistant.auth.service import create_access_token, issue_tokens
from assistant.invites.service import create_invite
from assistant.models.schema import Invite, InviteState, User

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session


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
    assert data["firstname"] == "Jane"
    assert "uid" in data
    assert "password" not in data


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


def test_register_auto_logs_in(client: TestClient) -> None:
    response = _register(client)
    assert response.status_code == 201
    assert "access_token" in client.cookies


# --- Registration mode matrix ---


def test_register_open_registration_succeeds(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REGISTRATION_REGISTRATION_ENABLED", "true")
    monkeypatch.setenv("REGISTRATION_INVITES_ENABLED", "true")
    response = _register(client)
    assert response.status_code == 201
    assert "access_token" in client.cookies


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
    invite = create_invite(
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
    assert "access_token" in client.cookies

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
    invite = create_invite(
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
    invite = create_invite(
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
    used = create_invite(db_session, inviter, "invitee5@example.com", config)
    sibling = create_invite(db_session, other_inviter, "invitee5@example.com", config)
    db_session.commit()

    response = _register(client, email="invitee5@example.com", invite_id=str(used.id))
    assert response.status_code == 201

    db_session.refresh(used)
    db_session.refresh(sibling)
    assert used.state == InviteState.CONVERTED.value
    assert sibling.state == InviteState.VOID.value


# --- Login ---


def test_login_sets_cookies(client: TestClient) -> None:
    _register(client)
    response = client.post(
        "/auth/login",
        json={"email": "user@example.com", "password": "secret123"},
    )
    assert response.status_code == 200
    assert "access_token" in client.cookies
    assert response.json()["email"] == "user@example.com"


def test_login_wrong_password(client: TestClient) -> None:
    _register(client)
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


def test_logout_clears_cookies(client: TestClient) -> None:
    _register(client)
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
