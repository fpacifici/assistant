"""Tests for the tag endpoints and tags on note responses."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from assistant.notes.service import create_note, create_notebook
from assistant.notes.tags import add_tag_to_note, find_or_create_tag

if TYPE_CHECKING:
    from collections.abc import Iterator

    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from assistant.models.schema import Note, User


@pytest.fixture(autouse=True)
def mock_send_email() -> Iterator[MagicMock]:
    with patch("assistant.email.service.send_email") as mock_send:
        yield mock_send


def _make_note(session: Session, owner: User) -> Note:
    notebook = create_notebook(session, "NB", owner)
    return create_note(session, notebook_id=notebook.id, owner=owner, title="N")


def _note_tag_url(note: Note) -> str:
    return f"/notebook/{note.notebook_id}/note/{note.id}/tag"


# --- Tag vocabulary ---


def test_create_tag_returns_201_then_200_for_existing(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    first = client.post("/tag", json={"name": " Work "}, headers=auth_headers)
    second = client.post("/tag", json={"name": "work"}, headers=auth_headers)

    assert first.status_code == 201
    assert first.json()["name"] == "Work"
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]


def test_create_tag_with_blank_name_is_422(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = client.post("/tag", json={"name": "   "}, headers=auth_headers)
    assert response.status_code == 422


def test_list_tags_returns_only_callers_tags(
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    other_user: User,
    db_session: Session,
) -> None:
    find_or_create_tag(db_session, test_user, "mine")
    find_or_create_tag(db_session, other_user, "theirs")

    response = client.get("/tag", headers=auth_headers)

    assert response.status_code == 200
    assert [t["name"] for t in response.json()] == ["mine"]


def test_tag_endpoints_require_auth(client: TestClient) -> None:
    assert client.get("/tag").status_code == 401


# --- Tagging notes ---


def test_add_tag_by_name_creates_and_returns_note_tags(
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    db_session: Session,
) -> None:
    note = _make_note(db_session, test_user)

    response = client.post(
        _note_tag_url(note), json={"name": "ideas"}, headers=auth_headers
    )

    assert response.status_code == 200
    assert [t["name"] for t in response.json()] == ["ideas"]
    vocabulary = client.get("/tag", headers=auth_headers).json()
    assert [t["name"] for t in vocabulary] == ["ideas"]


def test_add_tag_by_id(
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    db_session: Session,
) -> None:
    note = _make_note(db_session, test_user)
    tag, _ = find_or_create_tag(db_session, test_user, "ideas")

    response = client.post(
        _note_tag_url(note), json={"tag_id": str(tag.id)}, headers=auth_headers
    )

    assert response.status_code == 200
    assert response.json() == [{"id": str(tag.id), "name": "ideas"}]


@pytest.mark.parametrize("body", [{}, {"tag_id": str(uuid.uuid4()), "name": "x"}])
def test_add_tag_requires_exactly_one_of_id_or_name(
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    db_session: Session,
    body: dict[str, str],
) -> None:
    note = _make_note(db_session, test_user)
    response = client.post(_note_tag_url(note), json=body, headers=auth_headers)
    assert response.status_code == 422


def test_add_another_users_tag_is_404(
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    other_user: User,
    db_session: Session,
) -> None:
    note = _make_note(db_session, test_user)
    their_tag, _ = find_or_create_tag(db_session, other_user, "theirs")

    response = client.post(
        _note_tag_url(note), json={"tag_id": str(their_tag.id)}, headers=auth_headers
    )

    assert response.status_code == 404


def test_tagging_an_inaccessible_note_is_404(
    client: TestClient,
    other_auth_headers: dict[str, str],
    test_user: User,
    db_session: Session,
) -> None:
    note = _make_note(db_session, test_user)

    response = client.post(
        _note_tag_url(note), json={"name": "x"}, headers=other_auth_headers
    )

    assert response.status_code == 404


def test_remove_tag(
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    db_session: Session,
) -> None:
    note = _make_note(db_session, test_user)
    tag = add_tag_to_note(db_session, test_user, note.id, name="ideas")

    response = client.delete(f"{_note_tag_url(note)}/{tag.id}", headers=auth_headers)

    assert response.status_code == 204
    note_response = client.get(
        f"/notebook/{note.notebook_id}/note/{note.id}", headers=auth_headers
    )
    assert note_response.json()["tags"] == []


# --- Tags on note responses ---


def test_note_responses_include_callers_tags(  # noqa: PLR0913
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
    test_user: User,
    other_user: User,
    db_session: Session,
) -> None:
    note = _make_note(db_session, test_user)
    add_tag_to_note(db_session, test_user, note.id, name="b")
    add_tag_to_note(db_session, test_user, note.id, name="a")
    share = client.post(
        f"/notebook/{note.notebook_id}/note/{note.id}/share",
        json={"email": other_user.email, "role": "note_viewer"},
        headers=auth_headers,
    )
    assert share.status_code == 201
    other_tag = client.post(
        _note_tag_url(note), json={"name": "c"}, headers=other_auth_headers
    )
    assert other_tag.status_code == 200

    single = client.get(
        f"/notebook/{note.notebook_id}/note/{note.id}", headers=auth_headers
    )
    listed = client.get(f"/notebook/{note.notebook_id}/note", headers=auth_headers)
    as_other = client.get(
        f"/notebook/{note.notebook_id}/note/{note.id}", headers=other_auth_headers
    )

    assert [t["name"] for t in single.json()["tags"]] == ["a", "b"]
    assert [t["name"] for t in listed.json()[0]["tags"]] == ["a", "b"]
    # Copied from the sharer on share, plus the recipient's own tag.
    assert [t["name"] for t in as_other.json()["tags"]] == ["a", "b", "c"]
