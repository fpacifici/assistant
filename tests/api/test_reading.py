"""Tests for the reading list endpoints.

An error response rolls the test session back, users included, so a test that
goes on after one commits first (to the test's savepoint).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from assistant.models.schema import (
    Category,
    ReadingLink,
    ReadingLinkState,
)
from assistant.notes.user_service import delete_user

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from assistant.models.schema import User

Headers = dict[str, str]
URL = "https://example.com/article"


def _add(client: TestClient, headers: Headers, url: str = URL) -> dict:
    response = client.post("/reading/link", json={"url": url}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _category(session: Session, owner: User, name: str = "Tech") -> Category:
    category = Category(owner_id=owner.uid, name=name)
    session.add(category)
    session.flush()
    return category


def _link(  # noqa: PLR0913
    session: Session,
    owner: User,
    key: str,
    *,
    state: ReadingLinkState = ReadingLinkState.TO_READ,
    category: Category | None = None,
    created_at: datetime | None = None,
    decided_at: datetime | None = None,
) -> ReadingLink:
    link = ReadingLink(
        owner_id=owner.uid,
        url=f"https://example.com/{key}",
        url_key=key,
        state=state.value,
        category_id=category.id if category else None,
        created_at=created_at or datetime.now(UTC),
        decided_at=decided_at,
    )
    session.add(link)
    session.flush()
    return link


def _ids(client: TestClient, headers: Headers, **params: object) -> list[str]:
    response = client.get("/reading/link", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return [link["id"] for link in response.json()["links"]]


# --- Adding ---


def test_add_link_is_pending_and_to_read(
    client: TestClient, auth_headers: Headers
) -> None:
    link = _add(client, auth_headers, "https://example.com/article?utm_source=feed")
    assert link["url"] == URL
    assert link["analysis_status"] == "pending"
    assert link["state"] == "to_read"
    assert link["title"] is None
    assert link["category_id"] is None
    assert link["link_type"] is None


def test_duplicate_points_to_the_existing_link(
    client: TestClient, auth_headers: Headers, db_session: Session
) -> None:
    first = _add(client, auth_headers)
    db_session.commit()
    again = client.post(
        "/reading/link", json={"url": "http://EXAMPLE.com/article/"}, headers=auth_headers
    )
    assert again.status_code == 409
    assert again.json()["link_id"] == first["id"]


def test_duplicate_counts_in_any_state(
    client: TestClient, auth_headers: Headers, db_session: Session
) -> None:
    first = _add(client, auth_headers)
    client.post(f"/reading/link/{first['id']}/discard", headers=auth_headers)
    db_session.commit()
    again = client.post("/reading/link", json={"url": URL}, headers=auth_headers)
    assert again.status_code == 409


def test_two_users_can_save_the_same_url(
    client: TestClient, auth_headers: Headers, other_auth_headers: Headers
) -> None:
    _add(client, auth_headers)
    _add(client, other_auth_headers)


def test_invalid_url_is_refused(client: TestClient, auth_headers: Headers) -> None:
    response = client.post(
        "/reading/link", json={"url": "ftp://example.com/x"}, headers=auth_headers
    )
    assert response.status_code == 422
    assert "http" in response.json()["detail"]


# --- Listing ---


def test_to_read_is_oldest_first_and_paged(
    client: TestClient, auth_headers: Headers, db_session: Session, test_user: User
) -> None:
    now = datetime.now(UTC)
    links = [
        _link(db_session, test_user, f"k{i}", created_at=now - timedelta(minutes=10 - i))
        for i in range(5)
    ]
    first = client.get("/reading/link", params={"limit": 2}, headers=auth_headers).json()
    assert [link["id"] for link in first["links"]] == [str(links[0].id), str(links[1].id)]
    rest = _ids(client, auth_headers, limit=10, cursor=first["next_cursor"])
    assert rest == [str(link.id) for link in links[2:]]


def test_archive_is_most_recently_discarded_first(
    client: TestClient, auth_headers: Headers, db_session: Session, test_user: User
) -> None:
    now = datetime.now(UTC)
    old = _link(
        db_session,
        test_user,
        "old",
        state=ReadingLinkState.DISCARDED,
        decided_at=now - timedelta(days=1),
    )
    recent = _link(
        db_session, test_user, "recent", state=ReadingLinkState.DISCARDED, decided_at=now
    )
    _link(db_session, test_user, "unread")
    page = client.get(
        "/reading/link", params={"state": "discarded", "limit": 1}, headers=auth_headers
    ).json()
    assert [link["id"] for link in page["links"]] == [str(recent.id)]
    rest = _ids(client, auth_headers, state="discarded", cursor=page["next_cursor"])
    assert rest == [str(old.id)]


def test_filter_by_category_and_unfiled(
    client: TestClient, auth_headers: Headers, db_session: Session, test_user: User
) -> None:
    category = _category(db_session, test_user)
    filed = _link(db_session, test_user, "filed", category=category)
    unfiled = _link(db_session, test_user, "unfiled")
    assert _ids(client, auth_headers, category_id=category.id) == [str(filed.id)]
    assert _ids(client, auth_headers, unfiled=True) == [str(unfiled.id)]


def test_category_and_unfiled_together_are_refused(
    client: TestClient, auth_headers: Headers, db_session: Session, test_user: User
) -> None:
    category = _category(db_session, test_user)
    response = client.get(
        "/reading/link",
        params={"category_id": category.id, "unfiled": True},
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_bad_cursor_is_refused(client: TestClient, auth_headers: Headers) -> None:
    response = client.get(
        "/reading/link", params={"cursor": "not-a-cursor"}, headers=auth_headers
    )
    assert response.status_code == 422


def test_counts_per_category(
    client: TestClient, auth_headers: Headers, db_session: Session, test_user: User
) -> None:
    category = _category(db_session, test_user)
    _link(db_session, test_user, "a", category=category)
    _link(db_session, test_user, "b", category=category)
    _link(db_session, test_user, "c")
    _link(db_session, test_user, "d", state=ReadingLinkState.DISCARDED)
    counts = client.get("/reading/link/counts", headers=auth_headers).json()
    assert {(c["category_id"], c["count"]) for c in counts} == {
        (str(category.id), 2),
        (None, 1),
    }
    archived = client.get(
        "/reading/link/counts", params={"state": "discarded"}, headers=auth_headers
    ).json()
    assert archived == [{"category_id": None, "count": 1}]


# --- Editing ---


def test_edit_title_category_and_notes(
    client: TestClient, auth_headers: Headers, db_session: Session, test_user: User
) -> None:
    category = _category(db_session, test_user)
    link = _add(client, auth_headers)
    url = f"/reading/link/{link['id']}"
    edited = client.patch(
        url,
        json={
            "title": "  My title ",
            "category_id": str(category.id),
            "user_notes": "Read section 3",
        },
        headers=auth_headers,
    ).json()
    assert edited["title"] == "My title"
    assert edited["category_id"] == str(category.id)
    assert edited["user_notes"] == "Read section 3"
    row = db_session.get(ReadingLink, uuid.UUID(link["id"]))
    assert row is not None
    assert row.title_edited
    assert row.category_set_by_user

    cleared = client.patch(
        url, json={"title": "", "category_id": None}, headers=auth_headers
    ).json()
    assert cleared["title"] is None
    assert cleared["category_id"] is None
    assert cleared["user_notes"] == "Read section 3"
    db_session.refresh(row)
    assert not row.title_edited
    assert row.category_set_by_user


def test_cannot_move_into_another_users_category(
    client: TestClient, auth_headers: Headers, db_session: Session, other_user: User
) -> None:
    category = _category(db_session, other_user)
    link = _add(client, auth_headers)
    response = client.patch(
        f"/reading/link/{link['id']}",
        json={"category_id": str(category.id)},
        headers=auth_headers,
    )
    assert response.status_code == 404


# --- States ---


def test_discard_restore_and_delete(client: TestClient, auth_headers: Headers) -> None:
    link = _add(client, auth_headers)
    url = f"/reading/link/{link['id']}"
    discarded = client.post(f"{url}/discard", headers=auth_headers).json()
    assert discarded["state"] == "discarded"
    assert discarded["decided_at"] is not None
    restored = client.post(f"{url}/restore", headers=auth_headers).json()
    assert restored["state"] == "to_read"
    assert restored["decided_at"] is None
    client.post(f"{url}/discard", headers=auth_headers)
    assert client.delete(url, headers=auth_headers).status_code == 204
    assert client.get(url, headers=auth_headers).status_code == 404


def test_a_link_to_read_cannot_be_deleted_or_restored(
    client: TestClient, auth_headers: Headers, db_session: Session
) -> None:
    link = _add(client, auth_headers)
    db_session.commit()
    url = f"/reading/link/{link['id']}"
    deleted = client.delete(url, headers=auth_headers)
    assert deleted.status_code == 409
    assert "still to read" in deleted.json()["detail"]
    assert client.post(f"{url}/restore", headers=auth_headers).status_code == 409


def test_a_promoted_link_is_final_but_can_be_deleted(
    client: TestClient, auth_headers: Headers, db_session: Session, test_user: User
) -> None:
    link = _link(db_session, test_user, "p", state=ReadingLinkState.PROMOTED)
    db_session.commit()
    url = f"/reading/link/{link.id}"
    assert client.post(f"{url}/discard", headers=auth_headers).status_code == 409
    assert client.post(f"{url}/restore", headers=auth_headers).status_code == 409
    assert client.delete(url, headers=auth_headers).status_code == 204


# --- Categories and users ---


def test_deleting_a_category_moves_links_to_unfiled(
    client: TestClient, auth_headers: Headers, db_session: Session, test_user: User
) -> None:
    category = _category(db_session, test_user)
    link = _link(db_session, test_user, "a", category=category)
    assert client.delete(
        f"/category/{category.id}", headers=auth_headers
    ).status_code == (204)
    read = client.get(f"/reading/link/{link.id}", headers=auth_headers).json()
    assert read["category_id"] is None


def test_deleting_a_user_deletes_their_links(
    client: TestClient, auth_headers: Headers, db_session: Session, test_user: User
) -> None:
    _add(client, auth_headers)
    delete_user(db_session, test_user.uid)
    assert db_session.query(ReadingLink).count() == 0


# --- Ownership ---


def test_another_users_link_is_not_found(
    client: TestClient,
    auth_headers: Headers,
    other_auth_headers: Headers,
    db_session: Session,
) -> None:
    link = _add(client, auth_headers)
    db_session.commit()
    url = f"/reading/link/{link['id']}"
    other = other_auth_headers
    assert client.get(url, headers=other).status_code == 404
    assert client.patch(url, json={"title": "x"}, headers=other).status_code == 404
    assert client.post(f"{url}/discard", headers=other).status_code == 404
    assert client.delete(url, headers=other).status_code == 404
    assert _ids(client, other) == []


def test_requires_authentication(client: TestClient) -> None:
    assert client.get("/reading/link").status_code == 401
    assert client.post("/reading/link", json={"url": URL}).status_code == 401
