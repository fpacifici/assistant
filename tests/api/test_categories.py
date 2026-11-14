"""Tests for the category endpoints.

An error response rolls the test session back, users included, so a test that
goes on after one commits first (to the test's savepoint).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from assistant.blogs.discovery import ResolvedSource
from assistant.models.schema import BlogSourceKind, Category
from assistant.notes.user_service import delete_user

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from assistant.models.schema import User

Headers = dict[str, str]


@pytest.fixture(autouse=True)
def resolver() -> Iterator[MagicMock]:
    with patch("assistant.blogs.service.resolve_source") as resolve:
        resolve.return_value = ResolvedSource(
            "https://blog.example.com/feed.xml", BlogSourceKind.FEED, "Example Blog"
        )
        yield resolve


def _make_category(
    client: TestClient,
    headers: Headers,
    name: str = "Tech",
    description: str | None = None,
) -> dict:
    response = client.post(
        "/category", json={"name": name, "description": description}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


# --- Creating and listing ---


def test_create_and_list_categories(client: TestClient, auth_headers: Headers) -> None:
    _make_category(client, auth_headers, "zebra")
    _make_category(client, auth_headers, "Apple", "Fruit and orchards")
    listed = client.get("/category", headers=auth_headers).json()
    assert [(c["name"], c["description"]) for c in listed] == [
        ("Apple", "Fruit and orchards"),
        ("zebra", None),
    ]


def test_blank_description_counts_as_none(
    client: TestClient, auth_headers: Headers
) -> None:
    assert _make_category(client, auth_headers, description="   ")["description"] is None


def test_category_name_is_unique_per_user(
    client: TestClient,
    auth_headers: Headers,
    other_auth_headers: Headers,
    db_session: Session,
) -> None:
    _make_category(client, auth_headers)
    db_session.commit()
    again = client.post("/category", json={"name": "Tech"}, headers=auth_headers)
    assert again.status_code == 409
    assert "already exists" in again.json()["detail"]
    _make_category(client, other_auth_headers)


def test_blank_category_name_is_refused(
    client: TestClient, auth_headers: Headers
) -> None:
    response = client.post("/category", json={"name": "  "}, headers=auth_headers)
    assert response.status_code == 422


# --- Updating ---


def test_rename_and_describe_category(
    client: TestClient, auth_headers: Headers, db_session: Session
) -> None:
    first = _make_category(client, auth_headers, "One")
    _make_category(client, auth_headers, "Two")
    db_session.commit()
    url = f"/category/{first['id']}"
    assert client.put(url, json={"name": "Two"}, headers=auth_headers).status_code == 409
    assert client.put(url, json={"name": "One"}, headers=auth_headers).status_code == 200
    updated = client.put(
        url, json={"name": "Three", "description": "Databases"}, headers=auth_headers
    ).json()
    assert (updated["name"], updated["description"]) == ("Three", "Databases")
    cleared = client.put(url, json={"name": "Three"}, headers=auth_headers).json()
    assert cleared["description"] is None


# --- Deleting ---


def test_deleting_a_category_moves_sources_to_unfiled(
    client: TestClient, auth_headers: Headers
) -> None:
    category = _make_category(client, auth_headers)
    source = client.post(
        "/blog/source",
        json={"url": "https://blog.example.com", "category_id": category["id"]},
        headers=auth_headers,
    ).json()
    assert source["category_id"] == category["id"]
    response = client.delete(f"/category/{category['id']}", headers=auth_headers)
    assert response.status_code == 204
    read = client.get(f"/blog/source/{source['id']}", headers=auth_headers)
    assert read.json()["category_id"] is None


def test_deleting_a_user_deletes_their_categories(
    client: TestClient,
    auth_headers: Headers,
    db_session: Session,
    test_user: User,
) -> None:
    _make_category(client, auth_headers)
    delete_user(db_session, test_user.uid)
    assert db_session.query(Category).count() == 0


# --- Ownership ---


def test_another_users_category_is_not_found(
    client: TestClient,
    auth_headers: Headers,
    other_auth_headers: Headers,
    db_session: Session,
) -> None:
    category = _make_category(client, auth_headers)
    db_session.commit()
    url = f"/category/{category['id']}"
    assert client.put(
        url, json={"name": "x"}, headers=other_auth_headers
    ).status_code == (404)
    assert client.delete(url, headers=other_auth_headers).status_code == 404
    assert client.get("/category", headers=other_auth_headers).json() == []


def test_requires_authentication(client: TestClient) -> None:
    assert client.get("/category").status_code == 401
