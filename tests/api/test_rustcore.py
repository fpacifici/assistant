"""Tests for the endpoints implemented in Rust. These call the real extension."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

# --- Greeting ---


def test_greeting_is_built_by_rust(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.get(
        "/rustcore/greeting", params={"name": "Ada"}, headers=auth_headers
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Hello, Ada!"}


def test_greeting_requires_authentication(client: TestClient) -> None:
    response = client.get("/rustcore/greeting", params={"name": "Ada"})

    assert response.status_code == 401


def test_greeting_rejects_an_empty_name(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.get("/rustcore/greeting", params={"name": ""}, headers=auth_headers)

    assert response.status_code == 422
