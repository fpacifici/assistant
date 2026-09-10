"""Tests for invite API endpoints."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from assistant.email.exceptions import EmailSendError
from assistant.invites.service import create_invite

if TYPE_CHECKING:
    from collections.abc import Iterator

    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from assistant.models.schema import User

_REGISTRATION_CONFIG = {
    "registration_enabled": True,
    "invites_enabled": True,
    "default_quota": 5,
    "expiry_days": 1,
}


@pytest.fixture(autouse=True)
def mock_send_invite_email() -> Iterator[MagicMock]:
    with patch("assistant.email.service.send_email") as mock_send:
        yield mock_send


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
    assert data["email_sent"] is True
    assert "url" not in data

    me = client.get("/auth/me", headers=auth_headers)
    assert me.json()["invite_quota_remaining"] == 4


def test_create_invite_reports_email_sent_false_on_send_failure(
    client: TestClient,
    db_session: Session,
    test_user: User,
    auth_headers: dict[str, str],
    mock_send_invite_email: MagicMock,
) -> None:
    mock_send_invite_email.side_effect = EmailSendError("boom")
    test_user.invite_quota_remaining = 5
    db_session.commit()

    response = client.post(
        "/invites",
        json={"invitee_email": "invitee@example.com"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert response.json()["email_sent"] is False

    invites = client.get("/invites", headers=auth_headers).json()
    assert len(invites) == 1


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
    invite, _ = create_invite(
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
    invite, _ = create_invite(
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
    invite, _ = create_invite(
        db_session, test_user, "invitee@example.com", _REGISTRATION_CONFIG
    )
    db_session.commit()

    response = client.get(f"/invites/{invite.id}/public")
    assert response.status_code == 200
    assert response.json() == {"valid": True, "invitee_email": "invitee@example.com"}


def test_get_invite_public_unknown(client: TestClient) -> None:
    response = client.get(f"/invites/{uuid.uuid4()}/public")
    assert response.status_code == 200
    assert response.json() == {"valid": False, "invitee_email": None}


def test_get_invite_public_void(
    client: TestClient, db_session: Session, test_user: User, auth_headers: dict[str, str]
) -> None:
    test_user.invite_quota_remaining = 5
    db_session.commit()
    invite, _ = create_invite(
        db_session, test_user, "invitee@example.com", _REGISTRATION_CONFIG
    )
    db_session.commit()
    client.delete(f"/invites/{invite.id}", headers=auth_headers)

    response = client.get(f"/invites/{invite.id}/public")
    assert response.status_code == 200
    assert response.json() == {"valid": False, "invitee_email": None}


# --- POST /invites/{id}/resend ---


def test_resend_invite_by_non_sender_returns_403(
    client: TestClient,
    db_session: Session,
    test_user: User,
    other_auth_headers: dict[str, str],
) -> None:
    test_user.invite_quota_remaining = 5
    db_session.commit()
    invite, _ = create_invite(
        db_session, test_user, "invitee@example.com", _REGISTRATION_CONFIG
    )
    db_session.commit()

    response = client.post(f"/invites/{invite.id}/resend", headers=other_auth_headers)
    assert response.status_code == 403


def test_resend_invite_for_voided_invite_returns_404(
    client: TestClient,
    db_session: Session,
    test_user: User,
    auth_headers: dict[str, str],
) -> None:
    test_user.invite_quota_remaining = 5
    db_session.commit()
    invite, _ = create_invite(
        db_session, test_user, "invitee@example.com", _REGISTRATION_CONFIG
    )
    db_session.commit()
    client.delete(f"/invites/{invite.id}", headers=auth_headers)

    response = client.post(f"/invites/{invite.id}/resend", headers=auth_headers)
    assert response.status_code == 404


def test_resend_invite_by_sender_succeeds(
    client: TestClient,
    db_session: Session,
    test_user: User,
    auth_headers: dict[str, str],
) -> None:
    test_user.invite_quota_remaining = 5
    db_session.commit()
    invite, _ = create_invite(
        db_session, test_user, "invitee@example.com", _REGISTRATION_CONFIG
    )
    db_session.commit()

    response = client.post(f"/invites/{invite.id}/resend", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["email_sent"] is True


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
