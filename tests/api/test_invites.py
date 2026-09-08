"""Tests for invite API endpoints."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

from assistant.invites.service import create_invite

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from assistant.models.schema import User

_REGISTRATION_CONFIG = {
    "registration_enabled": True,
    "invites_enabled": True,
    "default_quota": 5,
    "expiry_days": 1,
}


# --- POST /invites ---


def test_create_invite_succeeds_and_decrements_quota(
    client: TestClient,
    db_session: Session,
    test_user: User,
    auth_headers: dict[str, str],
) -> None:
    test_user.invite_quota_remaining = 5
    db_session.commit()

    response = client.post(
        "/invites",
        json={"invitee_email": "invitee@example.com"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["invitee_email"] == "invitee@example.com"
    assert data["state"] == "pending"
    assert "url" in data

    me = client.get("/auth/me", headers=auth_headers)
    assert me.json()["invite_quota_remaining"] == 4


def test_create_invite_at_zero_quota_returns_403(
    client: TestClient,
    db_session: Session,
    test_user: User,
    auth_headers: dict[str, str],
) -> None:
    test_user.invite_quota_remaining = 0
    db_session.commit()

    response = client.post(
        "/invites",
        json={"invitee_email": "invitee@example.com"},
        headers=auth_headers,
    )
    assert response.status_code == 403


# --- GET /invites ---


def test_list_invites_returns_only_callers_own(
    client: TestClient,
    db_session: Session,
    test_user: User,
    other_user: User,
    auth_headers: dict[str, str],
) -> None:
    test_user.invite_quota_remaining = 5
    other_user.invite_quota_remaining = 5
    db_session.commit()
    create_invite(db_session, test_user, "mine@example.com", _REGISTRATION_CONFIG)
    create_invite(db_session, other_user, "theirs@example.com", _REGISTRATION_CONFIG)
    db_session.commit()

    response = client.get("/invites", headers=auth_headers)
    assert response.status_code == 200
    emails = [i["invitee_email"] for i in response.json()]
    assert emails == ["mine@example.com"]


# --- DELETE /invites/{id} ---


def test_void_invite_by_non_sender_returns_403(
    client: TestClient,
    db_session: Session,
    test_user: User,
    other_auth_headers: dict[str, str],
) -> None:
    test_user.invite_quota_remaining = 5
    db_session.commit()
    invite = create_invite(
        db_session, test_user, "invitee@example.com", _REGISTRATION_CONFIG
    )
    db_session.commit()

    response = client.delete(f"/invites/{invite.id}", headers=other_auth_headers)
    assert response.status_code == 403


def test_void_invite_by_sender_succeeds_and_refunds(
    client: TestClient,
    db_session: Session,
    test_user: User,
    auth_headers: dict[str, str],
) -> None:
    test_user.invite_quota_remaining = 5
    db_session.commit()
    invite = create_invite(
        db_session, test_user, "invitee@example.com", _REGISTRATION_CONFIG
    )
    db_session.commit()

    response = client.delete(f"/invites/{invite.id}", headers=auth_headers)
    assert response.status_code == 204

    me = client.get("/auth/me", headers=auth_headers)
    assert me.json()["invite_quota_remaining"] == 5


# --- GET /invites/{id}/public ---


def test_get_invite_public_valid(
    client: TestClient, db_session: Session, test_user: User
) -> None:
    test_user.invite_quota_remaining = 5
    db_session.commit()
    invite = create_invite(
        db_session, test_user, "invitee@example.com", _REGISTRATION_CONFIG
    )
    db_session.commit()

    response = client.get(f"/invites/{invite.id}/public")
    assert response.status_code == 200
    # Never leak the invitee's email — there is no ownership verification,
    # so anyone with the link must supply their own email to register.
    assert response.json() == {"valid": True}


def test_get_invite_public_unknown(client: TestClient) -> None:
    response = client.get(f"/invites/{uuid.uuid4()}/public")
    assert response.status_code == 200
    assert response.json() == {"valid": False}


def test_get_invite_public_void(
    client: TestClient, db_session: Session, test_user: User, auth_headers: dict[str, str]
) -> None:
    test_user.invite_quota_remaining = 5
    db_session.commit()
    invite = create_invite(
        db_session, test_user, "invitee@example.com", _REGISTRATION_CONFIG
    )
    db_session.commit()
    client.delete(f"/invites/{invite.id}", headers=auth_headers)

    response = client.get(f"/invites/{invite.id}/public")
    assert response.status_code == 200
    assert response.json() == {"valid": False}


# --- GET /invites/config ---


@pytest.mark.parametrize(
    ("registration_enabled", "invites_enabled"),
    [("true", "true"), ("false", "true"), ("true", "false"), ("false", "false")],
)
def test_get_invites_config_reflects_env(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    registration_enabled: str,
    invites_enabled: str,
) -> None:
    monkeypatch.setenv("REGISTRATION_REGISTRATION_ENABLED", registration_enabled)
    monkeypatch.setenv("REGISTRATION_INVITES_ENABLED", invites_enabled)

    response = client.get("/invites/config")
    assert response.status_code == 200
    assert response.json() == {
        "registration_enabled": registration_enabled == "true",
        "invites_enabled": invites_enabled == "true",
    }
