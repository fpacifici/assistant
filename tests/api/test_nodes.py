"""Tests for Node API endpoints."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from assistant.models.schema import Entitlement, RoleName
from assistant.notes.service import (
    add_markdown_node,
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
    nb = create_notebook(db_session, "NB", user)
    note = create_note(db_session, nb.id, user, "Test Note")
    return nb, note


# --- List nodes ---


def test_list_nodes_empty(
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    db_session: Session,
) -> None:
    nb, note = _setup(db_session, test_user)
    response = client.get(f"/notebook/{nb.id}/note/{note.id}/node", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == []


def test_list_nodes_ordered(
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    db_session: Session,
) -> None:
    nb, note = _setup(db_session, test_user)
    add_text_node(db_session, note.id, test_user, "First")
    add_text_node(db_session, note.id, test_user, "Second")
    add_text_node(db_session, note.id, test_user, "Third")

    response = client.get(f"/notebook/{nb.id}/note/{note.id}/node", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    assert [n["payload"] for n in data] == ["First", "Second", "Third"]


def test_list_nodes_wrong_notebook(
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    db_session: Session,
) -> None:
    _nb, note = _setup(db_session, test_user)
    other_nb = create_notebook(db_session, "Other", test_user)
    response = client.get(
        f"/notebook/{other_nb.id}/note/{note.id}/node", headers=auth_headers
    )
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
    first = add_text_node(db_session, note.id, test_user, "First")
    add_text_node(db_session, note.id, test_user, "Third")

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
    _nb, note = _setup(db_session, test_user)
    other_nb = create_notebook(db_session, "Other", test_user)
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
    assert response.status_code == 401


# --- Update node ---


def test_update_node_payload(
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    db_session: Session,
) -> None:
    nb, note = _setup(db_session, test_user)
    node = add_text_node(db_session, note.id, test_user, "Old")

    response = client.patch(
        f"/notebook/{nb.id}/note/{note.id}/node/{node.id}",
        json={
            "type": "update",
            "payload": "New",
            "expected_version": 1,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["payload"] == "New"
    assert data["version"] == 2


def test_update_node_version_conflict(
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    db_session: Session,
) -> None:
    nb, note = _setup(db_session, test_user)
    node = add_text_node(db_session, note.id, test_user, "Old")

    response = client.patch(
        f"/notebook/{nb.id}/note/{note.id}/node/{node.id}",
        json={
            "type": "update",
            "payload": "New",
            "expected_version": 99,
        },
        headers=auth_headers,
    )
    assert response.status_code == 409


def test_update_node_wrong_notebook(
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    db_session: Session,
) -> None:
    _nb, note = _setup(db_session, test_user)
    other_nb = create_notebook(db_session, "Other", test_user)
    node = add_text_node(db_session, note.id, test_user, "Text")

    response = client.patch(
        f"/notebook/{other_nb.id}/note/{note.id}/node/{node.id}",
        json={
            "type": "update",
            "payload": "Sneaky",
            "expected_version": 1,
        },
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_update_node_wrong_note(
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    db_session: Session,
) -> None:
    nb, note = _setup(db_session, test_user)
    other_note = create_note(db_session, nb.id, test_user, "Other")
    node = add_text_node(db_session, note.id, test_user, "Text")

    response = client.patch(
        f"/notebook/{nb.id}/note/{other_note.id}/node/{node.id}",
        json={
            "type": "update",
            "payload": "Sneaky",
            "expected_version": 1,
        },
        headers=auth_headers,
    )
    assert response.status_code == 404


# --- Merge nodes ---


def test_merge_nodes(
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    db_session: Session,
) -> None:
    nb, note = _setup(db_session, test_user)
    target = add_text_node(db_session, note.id, test_user, "Hello ")
    source = add_text_node(db_session, note.id, test_user, "World")

    response = client.patch(
        f"/notebook/{nb.id}/note/{note.id}/node/{target.id}",
        json={
            "type": "merge",
            "source_node_id": str(source.id),
            "expected_version": 1,
            "source_expected_version": 1,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["payload"] == "Hello World"
    assert data["version"] == 2


def test_merge_version_conflict(
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    db_session: Session,
) -> None:
    nb, note = _setup(db_session, test_user)
    target = add_text_node(db_session, note.id, test_user, "A")
    source = add_text_node(db_session, note.id, test_user, "B")

    response = client.patch(
        f"/notebook/{nb.id}/note/{note.id}/node/{target.id}",
        json={
            "type": "merge",
            "source_node_id": str(source.id),
            "expected_version": 99,
            "source_expected_version": 1,
        },
        headers=auth_headers,
    )
    assert response.status_code == 409


def test_merge_source_not_in_note(
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    db_session: Session,
) -> None:
    nb, note = _setup(db_session, test_user)
    other_note = create_note(db_session, nb.id, test_user, "Other")
    target = add_text_node(db_session, note.id, test_user, "A")
    source = add_text_node(db_session, other_note.id, test_user, "B")

    response = client.patch(
        f"/notebook/{nb.id}/note/{note.id}/node/{target.id}",
        json={
            "type": "merge",
            "source_node_id": str(source.id),
            "expected_version": 1,
            "source_expected_version": 1,
        },
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_merge_source_not_found(
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    db_session: Session,
) -> None:
    nb, note = _setup(db_session, test_user)
    target = add_text_node(db_session, note.id, test_user, "A")

    response = client.patch(
        f"/notebook/{nb.id}/note/{note.id}/node/{target.id}",
        json={
            "type": "merge",
            "source_node_id": str(uuid.uuid4()),
            "expected_version": 1,
            "source_expected_version": 1,
        },
        headers=auth_headers,
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
    node = add_text_node(db_session, note.id, test_user, "HelloWorld")

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
    node = add_text_node(db_session, note.id, test_user, "HelloWorld")

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
    _nb, note = _setup(db_session, test_user)
    other_nb = create_notebook(db_session, "Other", test_user)
    node = add_text_node(db_session, note.id, test_user, "Text")

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
    auth_headers: dict[str, str],
    test_user: User,
    db_session: Session,
) -> None:
    nb, note = _setup(db_session, test_user)
    node = add_text_node(db_session, note.id, test_user, "Gone")

    response = client.delete(
        f"/notebook/{nb.id}/note/{note.id}/node/{node.id}",
        headers=auth_headers,
    )
    assert response.status_code == 204


def test_delete_node_idempotent(
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    db_session: Session,
) -> None:
    nb, note = _setup(db_session, test_user)
    response = client.delete(
        f"/notebook/{nb.id}/note/{note.id}/node/{uuid.uuid4()}",
        headers=auth_headers,
    )
    assert response.status_code == 204


def test_delete_node_wrong_notebook(
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    db_session: Session,
) -> None:
    _nb, note = _setup(db_session, test_user)
    other_nb = create_notebook(db_session, "Other", test_user)
    node = add_text_node(db_session, note.id, test_user, "Text")

    response = client.delete(
        f"/notebook/{other_nb.id}/note/{note.id}/node/{node.id}",
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_delete_node_wrong_note(
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    db_session: Session,
) -> None:
    """A node_id belonging to a different note than the URL's note_id is
    treated as not found, even when the caller can edit both notes."""
    nb, note = _setup(db_session, test_user)
    other_note = create_note(db_session, nb.id, test_user, "Other Note")
    node = add_text_node(db_session, other_note.id, test_user, "Text")

    response = client.delete(
        f"/notebook/{nb.id}/note/{note.id}/node/{node.id}",
        headers=auth_headers,
    )
    assert response.status_code == 404


# --- Markdown nodes ---


def test_create_markdown_node(
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    db_session: Session,
) -> None:
    nb, note = _setup(db_session, test_user)
    response = client.post(
        f"/notebook/{nb.id}/note/{note.id}/node",
        json={"payload": "# Title", "block_type": "heading"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["node_type"] == "markdown"
    assert data["block_type"] == "heading"
    assert data["payload"] == "# Title"


def test_create_markdown_node_invalid_block_type(
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    db_session: Session,
) -> None:
    nb, note = _setup(db_session, test_user)
    response = client.post(
        f"/notebook/{nb.id}/note/{note.id}/node",
        json={"payload": "text", "block_type": "invalid"},
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_update_markdown_node(
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    db_session: Session,
) -> None:
    nb, note = _setup(db_session, test_user)
    node = add_markdown_node(db_session, note.id, test_user, "old", "paragraph")

    response = client.patch(
        f"/notebook/{nb.id}/note/{note.id}/node/{node.id}",
        json={
            "type": "update",
            "payload": "# new heading",
            "block_type": "heading",
            "expected_version": 1,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["payload"] == "# new heading"
    assert data["block_type"] == "heading"
    assert data["version"] == 2


def test_list_nodes_includes_block_type(
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    db_session: Session,
) -> None:
    nb, note = _setup(db_session, test_user)
    add_text_node(db_session, note.id, test_user, "plain text")
    add_markdown_node(db_session, note.id, test_user, "# Title", "heading")

    response = client.get(f"/notebook/{nb.id}/note/{note.id}/node", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["block_type"] is None
    assert data[1]["block_type"] == "heading"


def test_create_markdown_node_with_position(
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    db_session: Session,
) -> None:
    nb, note = _setup(db_session, test_user)
    n1 = add_markdown_node(db_session, note.id, test_user, "# H1", "heading")
    add_markdown_node(db_session, note.id, test_user, "para", "paragraph")

    response = client.post(
        f"/notebook/{nb.id}/note/{note.id}/node",
        json={
            "payload": "> quote",
            "block_type": "blockquote",
            "after_node_id": str(n1.id),
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert response.json()["block_type"] == "blockquote"


# --- Authorization ---


def test_create_node_by_unrelated_user_returns_404(
    client: TestClient,
    test_user: User,
    other_auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    nb, note = _setup(db_session, test_user)

    response = client.post(
        f"/notebook/{nb.id}/note/{note.id}/node",
        json={"payload": "hi"},
        headers=other_auth_headers,
    )
    assert response.status_code == 404


def test_create_node_by_note_viewer_returns_403(
    client: TestClient,
    test_user: User,
    other_user: User,
    other_auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    nb, note = _setup(db_session, test_user)
    db_session.add(
        Entitlement(
            principal_id=other_user.uid,
            note_id=note.id,
            role_name=RoleName.NOTE_VIEWER.value,
        ),
    )
    db_session.flush()

    response = client.post(
        f"/notebook/{nb.id}/note/{note.id}/node",
        json={"payload": "hi"},
        headers=other_auth_headers,
    )
    assert response.status_code == 403
