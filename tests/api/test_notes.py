"""Tests for Note API endpoints."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from assistant.notes.service import create_note, create_notebook, get_ordered_nodes

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from assistant.models.schema import User


class TestCreateNote:
    def test_create_note(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        test_user: User,
        db_session: Session,
    ) -> None:
        nb = create_notebook(db_session, "NB", test_user.uid)
        response = client.post(
            f"/notebook/{nb.id}/note",
            json={"title": "My Note"},
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "My Note"
        assert data["notebook_id"] == str(nb.id)

    def test_create_note_creates_default_node(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        test_user: User,
        db_session: Session,
    ) -> None:
        nb = create_notebook(db_session, "NB", test_user.uid)
        response = client.post(
            f"/notebook/{nb.id}/note",
            json={"title": "My Note"},
            headers=auth_headers,
        )
        assert response.status_code == 201
        note_id = response.json()["id"]
        nodes = get_ordered_nodes(db_session, uuid.UUID(note_id))
        assert len(nodes) == 1
        assert nodes[0].payload == ""
        assert nodes[0].node_type == "text"

    def test_create_note_missing_header(
        self,
        client: TestClient,
        test_user: User,
        db_session: Session,
    ) -> None:
        nb = create_notebook(db_session, "NB", test_user.uid)
        response = client.post(
            f"/notebook/{nb.id}/note",
            json={"title": "My Note"},
        )
        assert response.status_code == 422


class TestListNotes:
    def test_list_notes(
        self,
        client: TestClient,
        test_user: User,
        db_session: Session,
    ) -> None:
        nb = create_notebook(db_session, "NB", test_user.uid)
        create_note(db_session, nb.id, test_user.uid, "Note1")
        create_note(db_session, nb.id, test_user.uid, "Note2")

        response = client.get(f"/notebook/{nb.id}/note")
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_list_notes_pagination(
        self,
        client: TestClient,
        test_user: User,
        db_session: Session,
    ) -> None:
        nb = create_notebook(db_session, "NB", test_user.uid)
        for i in range(5):
            create_note(db_session, nb.id, test_user.uid, f"Note{i}")

        response = client.get(
            f"/notebook/{nb.id}/note",
            params={"offset": 0, "limit": 3},
        )
        assert response.status_code == 200
        assert len(response.json()) == 3


class TestGetNote:
    def test_get_note(
        self,
        client: TestClient,
        test_user: User,
        db_session: Session,
    ) -> None:
        nb = create_notebook(db_session, "NB", test_user.uid)
        note = create_note(db_session, nb.id, test_user.uid, "Test")

        response = client.get(f"/notebook/{nb.id}/note/{note.id}")
        assert response.status_code == 200
        assert response.json()["title"] == "Test"

    def test_get_note_wrong_notebook(
        self,
        client: TestClient,
        test_user: User,
        db_session: Session,
    ) -> None:
        nb1 = create_notebook(db_session, "NB1", test_user.uid)
        nb2 = create_notebook(db_session, "NB2", test_user.uid)
        note = create_note(db_session, nb1.id, test_user.uid, "Test")

        response = client.get(f"/notebook/{nb2.id}/note/{note.id}")
        assert response.status_code == 404

    def test_get_note_not_found(
        self,
        client: TestClient,
        test_user: User,
        db_session: Session,
    ) -> None:
        nb = create_notebook(db_session, "NB", test_user.uid)
        response = client.get(f"/notebook/{nb.id}/note/{uuid.uuid4()}")
        assert response.status_code == 404


class TestUpdateNote:
    def test_update_note(
        self,
        client: TestClient,
        test_user: User,
        db_session: Session,
    ) -> None:
        nb = create_notebook(db_session, "NB", test_user.uid)
        note = create_note(db_session, nb.id, test_user.uid, "Old")

        response = client.patch(
            f"/notebook/{nb.id}/note/{note.id}",
            json={"title": "New"},
        )
        assert response.status_code == 200
        assert response.json()["title"] == "New"

    def test_update_note_wrong_notebook(
        self,
        client: TestClient,
        test_user: User,
        db_session: Session,
    ) -> None:
        nb1 = create_notebook(db_session, "NB1", test_user.uid)
        nb2 = create_notebook(db_session, "NB2", test_user.uid)
        note = create_note(db_session, nb1.id, test_user.uid, "Test")

        response = client.patch(
            f"/notebook/{nb2.id}/note/{note.id}",
            json={"title": "Sneaky"},
        )
        assert response.status_code == 404


class TestDeleteNote:
    def test_delete_note(
        self,
        client: TestClient,
        test_user: User,
        db_session: Session,
    ) -> None:
        nb = create_notebook(db_session, "NB", test_user.uid)
        note = create_note(db_session, nb.id, test_user.uid, "Test")

        response = client.delete(
            f"/notebook/{nb.id}/note/{note.id}",
        )
        assert response.status_code == 204

        response = client.get(f"/notebook/{nb.id}/note/{note.id}")
        assert response.status_code == 404

    def test_delete_note_wrong_notebook(
        self,
        client: TestClient,
        test_user: User,
        db_session: Session,
    ) -> None:
        nb1 = create_notebook(db_session, "NB1", test_user.uid)
        nb2 = create_notebook(db_session, "NB2", test_user.uid)
        note = create_note(db_session, nb1.id, test_user.uid, "Test")

        response = client.delete(
            f"/notebook/{nb2.id}/note/{note.id}",
        )
        assert response.status_code == 404
