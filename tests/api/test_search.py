"""Tests for the search endpoint (against Postgres)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from assistant.models.schema import User
from assistant.notes.service import add_markdown_node, create_note, create_notebook
from assistant.notes.tags import add_tag_to_note
from tests.api.conftest import make_auth_headers

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

pytestmark = pytest.mark.postgres


@pytest.fixture
def owner(pg_session: Session) -> User:
    user = User(email="owner@example.com", firstname="O", lastname="W")
    pg_session.add(user)
    pg_session.flush()
    return user


# --- GET /search/notes ---


def test_search_requires_authentication(pg_client: TestClient) -> None:
    assert pg_client.get("/search/notes", params={"q": "berlin"}).status_code == 401


def test_empty_query_is_a_bad_request(pg_client: TestClient, owner: User) -> None:
    response = pg_client.get(
        "/search/notes",
        params={"q": "  "},
        headers=make_auth_headers(owner.uid),
    )

    assert response.status_code == 400


def test_search_returns_notes_with_highlighted_snippets(
    pg_client: TestClient,
    pg_session: Session,
    owner: User,
) -> None:
    notebook = create_notebook(pg_session, "Travel", owner)
    note = create_note(
        pg_session, notebook_id=notebook.id, owner=owner, title="Trip to Berlin"
    )
    node = add_markdown_node(pg_session, note.id, owner, "Fly to **Berlin**", "paragraph")
    tag = add_tag_to_note(pg_session, owner, note.id, name="travel")

    response = pg_client.get(
        "/search/notes",
        params={"q": "berlin ", "limit": 5},
        headers=make_auth_headers(owner.uid),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["unknown_tags"] == []
    assert body["offset"] == 0
    assert body["limit"] == 5
    [result] = body["results"]
    assert result["note"]["id"] == str(note.id)
    assert result["note"]["tags"] == [{"id": str(tag.id), "name": "travel"}]
    assert result["notebook"] == {"id": str(notebook.id), "name": "Travel"}
    assert result["title"] == [
        {"text": "Trip to ", "highlighted": False},
        {"text": "Berlin", "highlighted": True},
    ]
    assert result["snippets"] == [
        {
            "node_id": str(node.id),
            "segments": [
                {"text": "Fly to ", "highlighted": False},
                {"text": "Berlin", "highlighted": True},
            ],
        },
    ]


def test_unknown_tags_are_reported(pg_client: TestClient, owner: User) -> None:
    response = pg_client.get(
        "/search/notes",
        params={"q": "tag:nope"},
        headers=make_auth_headers(owner.uid),
    )

    assert response.status_code == 200
    assert response.json()["results"] == []
    assert response.json()["unknown_tags"] == ["nope"]


def test_invalid_sort_is_rejected(pg_client: TestClient, owner: User) -> None:
    response = pg_client.get(
        "/search/notes",
        params={"q": "berlin", "sort": "random"},
        headers=make_auth_headers(owner.uid),
    )

    assert response.status_code == 422
