"""Tests for the blog directory and source endpoints.

An error response rolls the test session back, users included, so a test that
goes on after one commits first (to the test's savepoint).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from assistant.blogs.discovery import ResolvedSource
from assistant.blogs.exceptions import SourceResolutionError
from assistant.models.schema import (
    BlogPost,
    BlogPostState,
    BlogPostStatus,
    BlogSource,
    BlogSourceKind,
)
from assistant.notes.user_service import delete_user

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from assistant.models.schema import User

FEED_URL = "https://blog.example.com/feed.xml"
Headers = dict[str, str]


@pytest.fixture(autouse=True)
def resolver() -> Iterator[MagicMock]:
    with patch("assistant.blogs.service.resolve_source") as resolve:
        resolve.return_value = ResolvedSource(
            FEED_URL, BlogSourceKind.FEED, "Example Blog"
        )
        yield resolve


def _make_source(client: TestClient, headers: Headers, **fields: object) -> dict:
    body = {"url": "https://blog.example.com", **fields}
    response = client.post("/blog/source", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _make_directory(client: TestClient, headers: Headers, name: str = "Tech") -> dict:
    response = client.post("/blog/directory", json={"name": name}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _add_post(
    session: Session,
    source_id: str,
    key: str,
    state: BlogPostState = BlogPostState.NEW,
) -> BlogPost:
    post = BlogPost(
        source_id=uuid.UUID(source_id),
        post_key=key,
        url=f"https://blog.example.com/{key}",
        published_at=datetime.now(UTC),
        status=BlogPostStatus.PROCESSED.value,
        state=state.value,
    )
    session.add(post)
    session.flush()
    return post


# --- Directories ---


def test_create_and_list_directories(client: TestClient, auth_headers: Headers) -> None:
    _make_directory(client, auth_headers, "zebra")
    _make_directory(client, auth_headers, "Apple")
    listed = client.get("/blog/directory", headers=auth_headers).json()
    assert [d["name"] for d in listed] == ["Apple", "zebra"]


def test_directory_name_is_unique_per_user(
    client: TestClient,
    auth_headers: Headers,
    other_auth_headers: Headers,
    db_session: Session,
) -> None:
    _make_directory(client, auth_headers)
    db_session.commit()
    again = client.post("/blog/directory", json={"name": "Tech"}, headers=auth_headers)
    assert again.status_code == 409
    _make_directory(client, other_auth_headers)


def test_blank_directory_name_is_refused(
    client: TestClient, auth_headers: Headers
) -> None:
    response = client.post("/blog/directory", json={"name": "  "}, headers=auth_headers)
    assert response.status_code == 422


def test_rename_directory(
    client: TestClient, auth_headers: Headers, db_session: Session
) -> None:
    first = _make_directory(client, auth_headers, "One")
    _make_directory(client, auth_headers, "Two")
    db_session.commit()
    url = f"/blog/directory/{first['id']}"
    assert (
        client.patch(url, json={"name": "Two"}, headers=auth_headers).status_code == 409
    )
    assert (
        client.patch(url, json={"name": "One"}, headers=auth_headers).status_code == 200
    )
    renamed = client.patch(url, json={"name": "Three"}, headers=auth_headers)
    assert renamed.json()["name"] == "Three"


def test_deleting_a_directory_moves_sources_to_unfiled(
    client: TestClient, auth_headers: Headers
) -> None:
    directory = _make_directory(client, auth_headers)
    source = _make_source(client, auth_headers, directory_id=directory["id"])
    response = client.delete(f"/blog/directory/{directory['id']}", headers=auth_headers)
    assert response.status_code == 204
    read = client.get(f"/blog/source/{source['id']}", headers=auth_headers)
    assert read.json()["directory_id"] is None


def test_another_users_directory_is_not_found(
    client: TestClient,
    auth_headers: Headers,
    other_auth_headers: Headers,
    db_session: Session,
) -> None:
    directory = _make_directory(client, auth_headers)
    db_session.commit()
    url = f"/blog/directory/{directory['id']}"
    assert (
        client.patch(url, json={"name": "x"}, headers=other_auth_headers).status_code
        == 404
    )
    assert client.delete(url, headers=other_auth_headers).status_code == 404
    assert client.get("/blog/directory", headers=other_auth_headers).json() == []


# --- Registering sources ---


def test_register_uses_resolved_values_and_defaults(
    client: TestClient, auth_headers: Headers, resolver: MagicMock
) -> None:
    before = datetime.now(UTC)
    source = _make_source(client, auth_headers)
    assert source["title"] == "Example Blog"
    assert source["feed_url"] == FEED_URL
    assert source["url"] == "https://blog.example.com"
    assert source["kind"] == "feed"
    assert source["enabled"] is True
    assert source["last_fetched_at"] is None
    collect_since = datetime.fromisoformat(source["collect_since"]).replace(tzinfo=UTC)
    assert before - timedelta(days=7, seconds=5) < collect_since
    assert collect_since < before - timedelta(days=6)
    resolver.assert_called_once_with("https://blog.example.com")


def test_register_keeps_the_users_fields(
    client: TestClient, auth_headers: Headers
) -> None:
    directory = _make_directory(client, auth_headers)
    source = _make_source(
        client,
        auth_headers,
        title="Mine",
        remarks="a note",
        preferences="only databases",
        directory_id=directory["id"],
        lookback_days=0,
    )
    assert source["title"] == "Mine"
    assert source["remarks"] == "a note"
    assert source["preferences"] == "only databases"
    assert source["directory_id"] == directory["id"]


def test_blank_preferences_count_as_none(
    client: TestClient, auth_headers: Headers
) -> None:
    source = _make_source(client, auth_headers, preferences="   ")
    assert source["preferences"] is None


def test_negative_look_back_is_refused(client: TestClient, auth_headers: Headers) -> None:
    response = client.post(
        "/blog/source",
        json={"url": "https://x.example", "lookback_days": -1},
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_resolution_failure_is_a_clear_error(
    client: TestClient, auth_headers: Headers, resolver: MagicMock
) -> None:
    resolver.side_effect = SourceResolutionError("No feed found at this URL")
    response = client.post(
        "/blog/source", json={"url": "https://x.example"}, headers=auth_headers
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "No feed found at this URL"


def test_same_resolved_feed_cannot_be_registered_twice(
    client: TestClient, auth_headers: Headers
) -> None:
    _make_source(client, auth_headers)
    response = client.post(
        "/blog/source", json={"url": "https://other.example"}, headers=auth_headers
    )
    assert response.status_code == 409


def test_two_users_can_register_the_same_feed(
    client: TestClient, auth_headers: Headers, other_auth_headers: Headers
) -> None:
    first = _make_source(client, auth_headers)
    second = _make_source(client, other_auth_headers)
    assert first["id"] != second["id"]


def test_register_into_another_users_directory_is_not_found(
    client: TestClient, auth_headers: Headers, other_auth_headers: Headers
) -> None:
    directory = _make_directory(client, auth_headers)
    response = client.post(
        "/blog/source",
        json={"url": "https://x.example", "directory_id": directory["id"]},
        headers=other_auth_headers,
    )
    assert response.status_code == 404


# --- Editing sources ---


def test_edit_pause_and_move(client: TestClient, auth_headers: Headers) -> None:
    directory = _make_directory(client, auth_headers)
    source = _make_source(client, auth_headers, preferences="old", remarks="keep")
    url = f"/blog/source/{source['id']}"
    edited = client.patch(
        url,
        json={
            "title": "New",
            "preferences": "new",
            "enabled": False,
            "directory_id": directory["id"],
        },
        headers=auth_headers,
    ).json()
    assert edited["title"] == "New"
    assert edited["preferences"] == "new"
    assert edited["enabled"] is False
    assert edited["directory_id"] == directory["id"]
    assert edited["remarks"] == "keep"

    moved = client.patch(url, json={"directory_id": None}, headers=auth_headers).json()
    assert moved["directory_id"] is None
    assert moved["title"] == "New"


def test_title_cannot_be_null(client: TestClient, auth_headers: Headers) -> None:
    source = _make_source(client, auth_headers)
    response = client.patch(
        f"/blog/source/{source['id']}", json={"title": None}, headers=auth_headers
    )
    assert response.status_code == 422


def test_collect_since_cannot_be_edited(
    client: TestClient, auth_headers: Headers
) -> None:
    source = _make_source(client, auth_headers)
    edited = client.patch(
        f"/blog/source/{source['id']}",
        json={"collect_since": "2000-01-01T00:00:00Z"},
        headers=auth_headers,
    ).json()
    assert edited["collect_since"].rstrip("Z") == source["collect_since"].rstrip("Z")


def test_another_users_source_is_not_found(
    client: TestClient,
    auth_headers: Headers,
    other_auth_headers: Headers,
    db_session: Session,
) -> None:
    source = _make_source(client, auth_headers)
    db_session.commit()
    url = f"/blog/source/{source['id']}"
    assert client.get(url, headers=other_auth_headers).status_code == 404
    assert (
        client.patch(url, json={"title": "x"}, headers=other_auth_headers).status_code
        == 404
    )
    assert client.delete(url, headers=other_auth_headers).status_code == 404
    assert client.get("/blog/source", headers=other_auth_headers).json() == []


def test_cannot_move_into_another_users_directory(
    client: TestClient, auth_headers: Headers, other_auth_headers: Headers
) -> None:
    source = _make_source(client, auth_headers)
    directory = _make_directory(client, other_auth_headers)
    response = client.patch(
        f"/blog/source/{source['id']}",
        json={"directory_id": directory["id"]},
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_requires_authentication(client: TestClient) -> None:
    assert client.get("/blog/source").status_code == 401
    assert client.get("/blog/directory").status_code == 401


# --- Deleting sources ---


def test_read_counts_useful_posts(
    client: TestClient, auth_headers: Headers, db_session: Session
) -> None:
    source = _make_source(client, auth_headers)
    _add_post(db_session, source["id"], "a", BlogPostState.USEFUL)
    _add_post(db_session, source["id"], "b", BlogPostState.NOT_USEFUL)
    read = client.get(f"/blog/source/{source['id']}", headers=auth_headers).json()
    assert read["useful_post_count"] == 1


def test_delete_everything(
    client: TestClient, auth_headers: Headers, db_session: Session
) -> None:
    source = _make_source(client, auth_headers)
    _add_post(db_session, source["id"], "a", BlogPostState.USEFUL)
    response = client.delete(f"/blog/source/{source['id']}", headers=auth_headers)
    assert response.status_code == 204
    assert db_session.get(BlogSource, uuid.UUID(source["id"])) is None
    assert db_session.query(BlogPost).count() == 0


def test_keep_useful_archives_the_source(
    client: TestClient, auth_headers: Headers, db_session: Session
) -> None:
    source = _make_source(client, auth_headers)
    useful = _add_post(db_session, source["id"], "a", BlogPostState.USEFUL)
    _add_post(db_session, source["id"], "b", BlogPostState.NEW)
    _add_post(db_session, source["id"], "c", BlogPostState.NOT_USEFUL)

    url = f"/blog/source/{source['id']}"
    response = client.delete(f"{url}?keep_useful=true", headers=auth_headers)
    assert response.status_code == 204
    db_session.commit()

    assert [post.id for post in db_session.query(BlogPost)] == [useful.id]
    assert client.get("/blog/source", headers=auth_headers).json() == []
    assert client.get(url, headers=auth_headers).status_code == 404
    archived = client.get("/blog/source?archived=true", headers=auth_headers).json()
    assert [s["title"] for s in archived] == ["Example Blog"]
    assert archived[0]["enabled"] is False
    assert archived[0]["archived_at"] is not None


def test_archived_source_leaves_filters_with_its_last_useful_post(
    client: TestClient, auth_headers: Headers, db_session: Session
) -> None:
    source = _make_source(client, auth_headers)
    post = _add_post(db_session, source["id"], "a", BlogPostState.USEFUL)
    client.delete(f"/blog/source/{source['id']}?keep_useful=true", headers=auth_headers)

    post.state = BlogPostState.NOT_USEFUL.value
    db_session.flush()
    assert client.get("/blog/source?archived=true", headers=auth_headers).json() == []


def test_keep_useful_with_nothing_useful_deletes(
    client: TestClient, auth_headers: Headers, db_session: Session
) -> None:
    source = _make_source(client, auth_headers)
    _add_post(db_session, source["id"], "a")
    client.delete(f"/blog/source/{source['id']}?keep_useful=true", headers=auth_headers)
    assert db_session.get(BlogSource, uuid.UUID(source["id"])) is None


def test_archived_feed_can_be_registered_again(
    client: TestClient, auth_headers: Headers, db_session: Session
) -> None:
    source = _make_source(client, auth_headers)
    _add_post(db_session, source["id"], "a", BlogPostState.USEFUL)
    client.delete(f"/blog/source/{source['id']}?keep_useful=true", headers=auth_headers)
    assert _make_source(client, auth_headers)["id"] != source["id"]


# --- Deleting users ---


def test_deleting_a_user_deletes_their_blogs(
    client: TestClient,
    auth_headers: Headers,
    db_session: Session,
    test_user: User,
) -> None:
    source = _make_source(client, auth_headers)
    _make_directory(client, auth_headers)
    _add_post(db_session, source["id"], "a")
    delete_user(db_session, test_user.uid)
    assert db_session.query(BlogSource).count() == 0
    assert db_session.query(BlogPost).count() == 0
