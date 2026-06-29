"""Tests for authentication API endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

from assistant.auth.service import create_access_token, issue_tokens
from assistant.models.schema import User

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session


def _register(client: TestClient, email: str = "user@example.com") -> dict:
    return client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "secret123",
            "firstname": "Jane",
            "lastname": "Doe",
        },
    )


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
