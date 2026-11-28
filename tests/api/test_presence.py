"""Tests for the presence and live note endpoints."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

from assistant.models.schema import RoleName
from assistant.notes.avatar_colors import AVATAR_COLORS
from assistant.notes.entitlements import grant_entitlement
from assistant.notes.service import add_markdown_node, create_note, create_notebook

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from assistant.models.schema import Note, User


@pytest.fixture
def shared_note(db_session: Session, test_user: User, other_user: User) -> Note:
    notebook = create_notebook(db_session, "NB", test_user)
    note = create_note(db_session, notebook.id, test_user, "Shared")
    grant_entitlement(
        db_session,
        test_user,
        note_id=note.id,
        grantee_email=other_user.email,
        role_name=RoleName.NOTE_EDITOR,
    )
    return note


def _note_url(note: Note) -> str:
    return f"/notebook/{note.notebook_id}/note/{note.id}"


# --- Heartbeat ---


def test_heartbeat_shows_the_user_to_others(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
    shared_note: Note,
    other_user: User,
) -> None:
    other_user.avatar_color = "teal"
    node_id = str(uuid.uuid4())
    response = client.put(
        f"{_note_url(shared_note)}/presence/{uuid.uuid4()}",
        json={"cursor": {"node_id": node_id, "offset": 3}},
        headers=other_auth_headers,
    )
    assert response.status_code == 204

    live = client.get(f"{_note_url(shared_note)}/live", headers=auth_headers).json()
    assert live["presence"] == [
        {
            "user_id": str(other_user.uid),
            "name": "Other User",
            "initial": "O",
            "color": AVATAR_COLORS["teal"],
            "cursor": {"node_id": node_id, "offset": 3},
        },
    ]


def test_heartbeat_without_cursor(
    client: TestClient, other_auth_headers: dict[str, str], shared_note: Note
) -> None:
    response = client.put(
        f"{_note_url(shared_note)}/presence/{uuid.uuid4()}",
        json={},
        headers=other_auth_headers,
    )
    assert response.status_code == 204


def test_heartbeat_rejects_a_negative_offset(
    client: TestClient, other_auth_headers: dict[str, str], shared_note: Note
) -> None:
    response = client.put(
        f"{_note_url(shared_note)}/presence/{uuid.uuid4()}",
        json={"cursor": {"node_id": str(uuid.uuid4()), "offset": -1}},
        headers=other_auth_headers,
    )
    assert response.status_code == 422


def test_heartbeat_on_an_invisible_note_is_404(
    client: TestClient,
    db_session: Session,
    test_user: User,
    other_auth_headers: dict[str, str],
    shared_note: Note,
) -> None:
    private = create_note(db_session, shared_note.notebook_id, test_user, "Private")

    response = client.put(
        f"{_note_url(private)}/presence/{uuid.uuid4()}",
        json={},
        headers=other_auth_headers,
    )
    assert response.status_code == 404


def test_heartbeat_with_another_users_client_id_is_409(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
    shared_note: Note,
) -> None:
    url = f"{_note_url(shared_note)}/presence/{uuid.uuid4()}"
    client.put(url, json={}, headers=other_auth_headers)

    assert client.put(url, json={}, headers=auth_headers).status_code == 409


def test_heartbeat_needs_authentication(client: TestClient, shared_note: Note) -> None:
    response = client.put(f"{_note_url(shared_note)}/presence/{uuid.uuid4()}", json={})
    assert response.status_code == 401


# --- Leave ---


def test_leave_hides_the_user(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
    shared_note: Note,
) -> None:
    url = f"{_note_url(shared_note)}/presence/{uuid.uuid4()}"
    client.put(url, json={}, headers=other_auth_headers)

    assert client.delete(url, headers=other_auth_headers).status_code == 204
    assert client.delete(url, headers=other_auth_headers).status_code == 204

    live = client.get(f"{_note_url(shared_note)}/live", headers=auth_headers).json()
    assert live["presence"] == []


# --- Live ---


def test_live_returns_nodes_then_none_at_the_same_revision(
    client: TestClient,
    db_session: Session,
    test_user: User,
    other_auth_headers: dict[str, str],
    shared_note: Note,
) -> None:
    add_markdown_node(db_session, shared_note.id, test_user, "Hello", "paragraph")

    first = client.get(
        f"{_note_url(shared_note)}/live", headers=other_auth_headers
    ).json()
    assert first["title"] == "Shared"
    assert [n["payload"] for n in first["nodes"]] == ["Hello"]

    second = client.get(
        f"{_note_url(shared_note)}/live",
        params={"since": first["revision"]},
        headers=other_auth_headers,
    ).json()
    assert second["nodes"] is None
    assert second["revision"] == first["revision"]


def test_live_returns_nodes_after_an_edit(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
    shared_note: Note,
) -> None:
    url = _note_url(shared_note)
    revision = client.get(f"{url}/live", headers=other_auth_headers).json()["revision"]

    client.post(
        f"{url}/node",
        json={"payload": "New", "block_type": "paragraph"},
        headers=auth_headers,
    )

    live = client.get(
        f"{url}/live", params={"since": revision}, headers=other_auth_headers
    ).json()
    assert live["revision"] != revision
    assert [n["payload"] for n in live["nodes"]] == ["New"]


def test_live_on_a_note_of_another_notebook_is_404(
    client: TestClient,
    db_session: Session,
    test_user: User,
    auth_headers: dict[str, str],
    shared_note: Note,
) -> None:
    other_notebook = create_notebook(db_session, "Other", test_user)

    response = client.get(
        f"/notebook/{other_notebook.id}/note/{shared_note.id}/live", headers=auth_headers
    )
    assert response.status_code == 404


# --- Notebook presence ---


def test_notebook_presence_lists_active_notes(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
    shared_note: Note,
    other_user: User,
) -> None:
    client.put(
        f"{_note_url(shared_note)}/presence/{uuid.uuid4()}",
        json={},
        headers=other_auth_headers,
    )

    response = client.get(
        f"/notebook/{shared_note.notebook_id}/presence", headers=auth_headers
    )

    assert response.status_code == 200
    [entry] = response.json()
    assert entry["note_id"] == str(shared_note.id)
    assert [u["user_id"] for u in entry["users"]] == [str(other_user.uid)]


def test_notebook_presence_excludes_the_caller(
    client: TestClient, auth_headers: dict[str, str], shared_note: Note
) -> None:
    client.put(
        f"{_note_url(shared_note)}/presence/{uuid.uuid4()}", json={}, headers=auth_headers
    )

    response = client.get(
        f"/notebook/{shared_note.notebook_id}/presence", headers=auth_headers
    )

    assert response.json() == []


def test_notebook_presence_of_an_invisible_notebook_is_404(
    client: TestClient,
    db_session: Session,
    test_user: User,
    other_auth_headers: dict[str, str],
) -> None:
    private = create_notebook(db_session, "Private", test_user)

    response = client.get(f"/notebook/{private.id}/presence", headers=other_auth_headers)

    assert response.status_code == 404
