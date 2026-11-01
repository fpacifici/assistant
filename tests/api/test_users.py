"""Tests for User API endpoints.

Every route requires authentication and only exposes or changes the caller's
own profile. There is no list or create route: account creation is
`POST /auth/register`, and the user directory cannot be enumerated.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from assistant.models.schema import User as UserModel

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from assistant.models.schema import User


class TestNoDirectoryAccess:
    """The list and create routes are gone; nothing may enumerate users."""

    def test_list_route_is_gone_unauthenticated(self, client: TestClient) -> None:
        response = client.get("/user")
        assert response.status_code != 200
        assert response.status_code in (404, 405)

    def test_list_route_is_gone_authenticated(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        # Even a logged-in caller cannot list the directory.
        response = client.get("/user", headers=auth_headers)
        assert response.status_code != 200
        assert response.status_code in (404, 405)

    def test_create_route_is_gone(self, client: TestClient) -> None:
        response = client.post(
            "/user",
            json={"email": "new@example.com", "firstname": "New", "lastname": "User"},
        )
        assert response.status_code != 201
        assert response.status_code in (404, 405)

    def test_create_route_is_gone_even_authenticated(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        response = client.post(
            "/user",
            json={"email": "new@example.com", "firstname": "New", "lastname": "User"},
            headers=auth_headers,
        )
        assert response.status_code != 201
        assert response.status_code in (404, 405)


class TestGetUser:
    def test_get_own_profile(
        self,
        client: TestClient,
        test_user: User,
        auth_headers: dict[str, str],
    ) -> None:
        response = client.get(f"/user/{test_user.uid}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "test@example.com"
        assert data["uid"] == str(test_user.uid)

    def test_get_user_unauthenticated(self, client: TestClient, test_user: User) -> None:
        # No email or any other field leaks without authentication.
        response = client.get(f"/user/{test_user.uid}")
        assert response.status_code == 401
        assert "test@example.com" not in response.text

    def test_get_other_real_user_forbidden(
        self,
        client: TestClient,
        test_user: User,  # noqa: ARG002
        other_user: User,
        auth_headers: dict[str, str],
    ) -> None:
        response = client.get(f"/user/{other_user.uid}", headers=auth_headers)
        assert response.status_code == 403
        assert "other@example.com" not in response.text

    def test_get_nonexistent_uid_forbidden_not_found(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        # A missing id and another user's id are indistinguishable: both 403,
        # so existence of an account is never confirmed.
        response = client.get(f"/user/{uuid.uuid4()}", headers=auth_headers)
        assert response.status_code == 403


class TestUpdateUser:
    def test_update_user_partial(
        self,
        client: TestClient,
        test_user: User,
        auth_headers: dict[str, str],
    ) -> None:
        response = client.patch(
            f"/user/{test_user.uid}",
            json={"firstname": "Updated"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["firstname"] == "Updated"
        assert data["lastname"] == "User"

    def test_update_user_unauthenticated(
        self, client: TestClient, test_user: User
    ) -> None:
        response = client.patch(
            f"/user/{test_user.uid}",
            json={"firstname": "Ghost"},
        )
        assert response.status_code == 401

    def test_update_user_nonexistent_uid_forbidden(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        response = client.patch(
            f"/user/{uuid.uuid4()}",
            json={"firstname": "Ghost"},
            headers=auth_headers,
        )
        assert response.status_code == 403

    def test_update_user_other_real_user_forbidden(
        self,
        client: TestClient,
        test_user: User,  # noqa: ARG002
        other_user: User,
        auth_headers: dict[str, str],
        db_session: Session,
    ) -> None:
        db_session.commit()
        response = client.patch(
            f"/user/{other_user.uid}",
            json={"firstname": "Hijacked"},
            headers=auth_headers,
        )
        assert response.status_code == 403
        db_session.refresh(other_user)
        assert other_user.firstname == "Other"

    def test_update_user_no_changes(
        self,
        client: TestClient,
        test_user: User,
        auth_headers: dict[str, str],
    ) -> None:
        response = client.patch(
            f"/user/{test_user.uid}",
            json={},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["email"] == "test@example.com"

    def test_update_user_duplicate_email(
        self,
        client: TestClient,
        test_user: User,
        auth_headers: dict[str, str],
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
            headers=auth_headers,
        )
        assert response.status_code == 409
