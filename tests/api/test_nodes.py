"""Tests for Node API endpoints."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from assistant.notes.service import (
    add_text_node,
    create_note,
    create_notebook,
)

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from assistant.models.schema import User


def _setup(
    db_session: Session,
    user: User,
) -> tuple:
    """Create a notebook, note, and return (notebook, note)."""
    nb = create_notebook(db_session, "NB", user.uid)
    note = create_note(db_session, nb.id, user.uid, "Test Note")
    return nb, note


# --- List nodes ---


def test_list_nodes_empty(
    client: TestClient,
    test_user: User,
    db_session: Session,
) -> None:
    nb, note = _setup(db_session, test_user)
    response = client.get(f"/notebook/{nb.id}/note/{note.id}/node")
    assert response.status_code == 200
    assert response.json() == []


def test_list_nodes_ordered(
    client: TestClient,
    test_user: User,
    db_session: Session,
) -> None:
    nb, note = _setup(db_session, test_user)
    add_text_node(db_session, note.id, test_user.uid, "First")
    add_text_node(db_session, note.id, test_user.uid, "Second")
    add_text_node(db_session, note.id, test_user.uid, "Third")

    response = client.get(f"/notebook/{nb.id}/note/{note.id}/node")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    assert [n["payload"] for n in data] == ["First", "Second", "Third"]


def test_list_nodes_wrong_notebook(
    client: TestClient,
    test_user: User,
    db_session: Session,
) -> None:
    _nb, note = _setup(db_session, test_user)
    other_nb = create_notebook(db_session, "Other", test_user.uid)
    response = client.get(f"/notebook/{other_nb.id}/note/{note.id}/node")
    assert response.status_code == 404


# --- Create node ---


def test_create_node_append(
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    db_session: Session,
) -> None:
    nb, note = _setup(db_session, test_user)
    response = client.post(
        f"/notebook/{nb.id}/note/{note.id}/node",
        json={"payload": "Hello world"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["payload"] == "Hello world"
    assert data["note_id"] == str(note.id)
    assert data["version"] == 1
    assert data["node_type"] == "text"


def test_create_node_insert_after(
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    db_session: Session,
) -> None:
    nb, note = _setup(db_session, test_user)
    first = add_text_node(db_session, note.id, test_user.uid, "First")
    add_text_node(db_session, note.id, test_user.uid, "Third")

    response = client.post(
        f"/notebook/{nb.id}/note/{note.id}/node",
        json={"payload": "Second", "after_node_id": str(first.id)},
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert response.json()["payload"] == "Second"


def test_create_node_wrong_notebook(
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    db_session: Session,
) -> None:
    nb, note = _setup(db_session, test_user)
    other_nb = create_notebook(db_session, "Other", test_user.uid)
    response = client.post(
        f"/notebook/{other_nb.id}/note/{note.id}/node",
        json={"payload": "Sneaky"},
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_create_node_missing_header(
    client: TestClient,
    test_user: User,
    db_session: Session,
) -> None:
    nb, note = _setup(db_session, test_user)
    response = client.post(
        f"/notebook/{nb.id}/note/{note.id}/node",
        json={"payload": "No auth"},
    )
    assert response.status_code == 422


# --- Update node ---


def test_update_node_payload(
    client: TestClient,
    test_user: User,
    db_session: Session,
) -> None:
    nb, note = _setup(db_session, test_user)
    node = add_text_node(db_session, note.id, test_user.uid, "Old")

    response = client.patch(
        f"/notebook/{nb.id}/note/{note.id}/node/{node.id}",
        json={
            "type": "update",
            "payload": "New",
            "expected_version": 1,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["payload"] == "New"
    assert data["version"] == 2


def test_update_node_version_conflict(
    client: TestClient,
    test_user: User,
    db_session: Session,
) -> None:
    nb, note = _setup(db_session, test_user)
    node = add_text_node(db_session, note.id, test_user.uid, "Old")

    response = client.patch(
        f"/notebook/{nb.id}/note/{note.id}/node/{node.id}",
        json={
            "type": "update",
            "payload": "New",
            "expected_version": 99,
        },
    )
    assert response.status_code == 409


def test_update_node_wrong_notebook(
    client: TestClient,
    test_user: User,
    db_session: Session,
) -> None:
    nb, note = _setup(db_session, test_user)
    other_nb = create_notebook(db_session, "Other", test_user.uid)
    node = add_text_node(db_session, note.id, test_user.uid, "Text")

    response = client.patch(
        f"/notebook/{other_nb.id}/note/{note.id}/node/{node.id}",
        json={
            "type": "update",
            "payload": "Sneaky",
            "expected_version": 1,
        },
    )
    assert response.status_code == 404


def test_update_node_wrong_note(
    client: TestClient,
    test_user: User,
    db_session: Session,
) -> None:
    nb, note = _setup(db_session, test_user)
    other_note = create_note(db_session, nb.id, test_user.uid, "Other")
    node = add_text_node(db_session, note.id, test_user.uid, "Text")

    response = client.patch(
        f"/notebook/{nb.id}/note/{other_note.id}/node/{node.id}",
        json={
            "type": "update",
            "payload": "Sneaky",
            "expected_version": 1,
        },
    )
    assert response.status_code == 404


# --- Merge nodes ---


def test_merge_nodes(
    client: TestClient,
    test_user: User,
    db_session: Session,
) -> None:
    nb, note = _setup(db_session, test_user)
    target = add_text_node(db_session, note.id, test_user.uid, "Hello ")
    source = add_text_node(db_session, note.id, test_user.uid, "World")

    response = client.patch(
        f"/notebook/{nb.id}/note/{note.id}/node/{target.id}",
        json={
            "type": "merge",
            "source_node_id": str(source.id),
            "expected_version": 1,
            "source_expected_version": 1,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["payload"] == "Hello World"
    assert data["version"] == 2


def test_merge_version_conflict(
    client: TestClient,
    test_user: User,
    db_session: Session,
) -> None:
    nb, note = _setup(db_session, test_user)
    target = add_text_node(db_session, note.id, test_user.uid, "A")
    source = add_text_node(db_session, note.id, test_user.uid, "B")

    response = client.patch(
        f"/notebook/{nb.id}/note/{note.id}/node/{target.id}",
        json={
            "type": "merge",
            "source_node_id": str(source.id),
            "expected_version": 99,
            "source_expected_version": 1,
        },
    )
    assert response.status_code == 409


def test_merge_source_not_in_note(
    client: TestClient,
    test_user: User,
    db_session: Session,
) -> None:
    nb, note = _setup(db_session, test_user)
    other_note = create_note(db_session, nb.id, test_user.uid, "Other")
    target = add_text_node(db_session, note.id, test_user.uid, "A")
    source = add_text_node(db_session, other_note.id, test_user.uid, "B")

    response = client.patch(
        f"/notebook/{nb.id}/note/{note.id}/node/{target.id}",
        json={
            "type": "merge",
            "source_node_id": str(source.id),
            "expected_version": 1,
            "source_expected_version": 1,
        },
    )
    assert response.status_code == 404


def test_merge_source_not_found(
    client: TestClient,
    test_user: User,
    db_session: Session,
) -> None:
    nb, note = _setup(db_session, test_user)
    target = add_text_node(db_session, note.id, test_user.uid, "A")

    response = client.patch(
        f"/notebook/{nb.id}/note/{note.id}/node/{target.id}",
        json={
            "type": "merge",
            "source_node_id": str(uuid.uuid4()),
            "expected_version": 1,
            "source_expected_version": 1,
        },
    )
    assert response.status_code == 404


# --- Split node ---


def test_split_node(
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    db_session: Session,
) -> None:
    nb, note = _setup(db_session, test_user)
    node = add_text_node(db_session, note.id, test_user.uid, "HelloWorld")

    response = client.post(
        f"/notebook/{nb.id}/note/{note.id}/node/{node.id}/split",
        json={"offset": 5, "expected_version": 1},
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["original"]["payload"] == "Hello"
    assert data["original"]["version"] == 2
    assert data["new"]["payload"] == "World"
    assert data["new"]["version"] == 1


def test_split_node_version_conflict(
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    db_session: Session,
) -> None:
    nb, note = _setup(db_session, test_user)
    node = add_text_node(db_session, note.id, test_user.uid, "HelloWorld")

    response = client.post(
        f"/notebook/{nb.id}/note/{note.id}/node/{node.id}/split",
        json={"offset": 5, "expected_version": 99},
        headers=auth_headers,
    )
    assert response.status_code == 409


def test_split_node_wrong_notebook(
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    db_session: Session,
) -> None:
    nb, note = _setup(db_session, test_user)
    other_nb = create_notebook(db_session, "Other", test_user.uid)
    node = add_text_node(db_session, note.id, test_user.uid, "Text")

    response = client.post(
        f"/notebook/{other_nb.id}/note/{note.id}/node/{node.id}/split",
        json={"offset": 2, "expected_version": 1},
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_split_node_not_found(
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    db_session: Session,
) -> None:
    nb, note = _setup(db_session, test_user)

    response = client.post(
        f"/notebook/{nb.id}/note/{note.id}/node/{uuid.uuid4()}/split",
        json={"offset": 2, "expected_version": 1},
        headers=auth_headers,
    )
    assert response.status_code == 404


# --- Delete node ---


def test_delete_node(
    client: TestClient,
    test_user: User,
    db_session: Session,
) -> None:
    nb, note = _setup(db_session, test_user)
    node = add_text_node(db_session, note.id, test_user.uid, "Gone")

    response = client.delete(
        f"/notebook/{nb.id}/note/{note.id}/node/{node.id}",
    )
    assert response.status_code == 204


def test_delete_node_idempotent(
    client: TestClient,
    test_user: User,
    db_session: Session,
) -> None:
    nb, note = _setup(db_session, test_user)
    response = client.delete(
        f"/notebook/{nb.id}/note/{note.id}/node/{uuid.uuid4()}",
    )
    assert response.status_code == 204


def test_delete_node_wrong_notebook(
    client: TestClient,
    test_user: User,
    db_session: Session,
) -> None:
    nb, note = _setup(db_session, test_user)
    other_nb = create_notebook(db_session, "Other", test_user.uid)
    node = add_text_node(db_session, note.id, test_user.uid, "Text")

    response = client.delete(
        f"/notebook/{other_nb.id}/note/{note.id}/node/{node.id}",
    )
    assert response.status_code == 404
