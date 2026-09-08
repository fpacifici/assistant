"""Tests for User API endpoints."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

from assistant.invites.service import create_invite
from assistant.models.schema import InviteState
from assistant.models.schema import User as UserModel

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from assistant.models.schema import User


class TestListUsers:
    def test_list_users_empty(self, client: TestClient) -> None:
        response = client.get("/user")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_users(
        self,
        client: TestClient,
        test_user: User,
    ) -> None:
        response = client.get("/user")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["uid"] == str(test_user.uid)

    def test_list_users_pagination(
        self,
        client: TestClient,
        test_user: User,  # noqa: ARG002
        db_session: Session,
    ) -> None:
        for i in range(4):
            other = UserModel(
                email=f"other{i}@example.com",
                firstname="O",
                lastname="U",
            )
            db_session.add(other)
        db_session.flush()

        response = client.get("/user", params={"limit": 2})
        assert response.status_code == 200
        assert len(response.json()) == 2


class TestCreateUser:
    def test_create_user(self, client: TestClient) -> None:
        response = client.post(
            "/user",
            json={
                "email": "new@example.com",
                "firstname": "New",
                "lastname": "User",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "new@example.com"
        assert data["firstname"] == "New"
        assert data["lastname"] == "User"
        assert "uid" in data

    def test_create_user_duplicate_email(
        self,
        client: TestClient,
        test_user: User,  # noqa: ARG002
    ) -> None:
        response = client.post(
            "/user",
            json={
                "email": "test@example.com",
                "firstname": "Dup",
                "lastname": "User",
            },
        )
        assert response.status_code == 409

    def test_create_user_registration_disabled_without_invite_rejected(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("REGISTRATION_REGISTRATION_ENABLED", "false")
        response = client.post(
            "/user",
            json={
                "email": "new@example.com",
                "firstname": "New",
                "lastname": "User",
            },
        )
        assert response.status_code == 403

    def test_create_user_registration_disabled_with_valid_invite_succeeds(
        self,
        client: TestClient,
        db_session: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        inviter = UserModel(
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
        response = client.post(
            "/user",
            json={
                "email": "invitee@example.com",
                "firstname": "New",
                "lastname": "User",
                "invite_id": str(invite.id),
            },
        )
        assert response.status_code == 201

        db_session.refresh(invite)
        assert invite.state == InviteState.CONVERTED.value


class TestGetUser:
    def test_get_user(
        self,
        client: TestClient,
        test_user: User,
    ) -> None:
        response = client.get(f"/user/{test_user.uid}")
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "test@example.com"
        assert data["uid"] == str(test_user.uid)

    def test_get_user_not_found(self, client: TestClient) -> None:
        response = client.get(f"/user/{uuid.uuid4()}")
        assert response.status_code == 404


class TestUpdateUser:
    def test_update_user_partial(
        self,
        client: TestClient,
        test_user: User,
    ) -> None:
        response = client.patch(
            f"/user/{test_user.uid}",
            json={"firstname": "Updated"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["firstname"] == "Updated"
        assert data["lastname"] == "User"

    def test_update_user_not_found(self, client: TestClient) -> None:
        response = client.patch(
            f"/user/{uuid.uuid4()}",
            json={"firstname": "Ghost"},
        )
        assert response.status_code == 404

    def test_update_user_no_changes(
        self,
        client: TestClient,
        test_user: User,
    ) -> None:
        response = client.patch(
            f"/user/{test_user.uid}",
            json={},
        )
        assert response.status_code == 200
        assert response.json()["email"] == "test@example.com"

    def test_update_user_duplicate_email(
        self,
        client: TestClient,
        test_user: User,
        db_session: Session,
    ) -> None:
        other = UserModel(
            email="other@example.com",
            firstname="Other",
            lastname="User",
        )
        db_session.add(other)
        db_session.flush()

        response = client.patch(
            f"/user/{test_user.uid}",
            json={"email": "other@example.com"},
        )
        assert response.status_code == 409
