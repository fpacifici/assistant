"""Tests for Notebook API endpoints."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from assistant.models.schema import Entitlement, RoleName
from assistant.models.schema import User as UserModel
from assistant.notes.service import create_notebook

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from assistant.models.schema import User

from tests.api.conftest import make_auth_headers


class TestCreateNotebook:
    def test_create_notebook(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
    ) -> None:
        response = client.post(
            "/notebook",
            json={"name": "My Notebook"},
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "My Notebook"
        assert "id" in data
        assert set(data["permissions"]) == {
            "view_notebook",
            "update_notebook",
            "delete_notebook",
            "create_notes",
            "list_notes",
            "own_notes",
            "delete_notes",
            "view_notes",
            "share_notebook",
        }

    def test_create_notebook_missing_header(
        self,
        client: TestClient,
    ) -> None:
        response = client.post(
            "/notebook",
            json={"name": "My Notebook"},
        )
        assert response.status_code == 401


class TestListNotebooks:
    def test_list_notebooks(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        test_user: User,
        db_session: Session,
    ) -> None:
        create_notebook(db_session, "NB1", test_user)
        create_notebook(db_session, "NB2", test_user)

        response = client.get("/notebook", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_list_notebooks_pagination(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        test_user: User,
        db_session: Session,
    ) -> None:
        for i in range(5):
            create_notebook(db_session, f"NB{i}", test_user)

        response = client.get(
            "/notebook",
            headers=auth_headers,
            params={"offset": 0, "limit": 2},
        )
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_list_notebooks_only_own(
        self,
        client: TestClient,
        test_user: User,
        db_session: Session,
    ) -> None:
        other = UserModel(
            email="other@test.com",
            firstname="Other",
            lastname="User",
        )
        db_session.add(other)
        db_session.flush()

        create_notebook(db_session, "Mine", test_user)
        create_notebook(db_session, "Theirs", other)

        response = client.get(
            "/notebook",
            headers=make_auth_headers(test_user.uid),
        )
        assert len(response.json()) == 1
        assert response.json()[0]["name"] == "Mine"


class TestGetNotebook:
    def test_get_notebook(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        test_user: User,
        db_session: Session,
    ) -> None:
        nb = create_notebook(db_session, "Test NB", test_user)
        response = client.get(f"/notebook/{nb.id}", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["name"] == "Test NB"

    def test_get_notebook_not_found(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
    ) -> None:
        response = client.get(f"/notebook/{uuid.uuid4()}", headers=auth_headers)
        assert response.status_code == 404

    def test_get_notebook_other_user_returns_404(
        self,
        client: TestClient,
        test_user: User,
        db_session: Session,
    ) -> None:
        other = UserModel(email="other2@test.com", firstname="O", lastname="U")
        db_session.add(other)
        db_session.flush()
        nb = create_notebook(db_session, "Other NB", other)

        response = client.get(
            f"/notebook/{nb.id}",
            headers=make_auth_headers(test_user.uid),
        )
        assert response.status_code == 404


class TestUpdateNotebook:
    def test_update_notebook(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        test_user: User,
        db_session: Session,
    ) -> None:
        nb = create_notebook(db_session, "Old Name", test_user)
        response = client.patch(
            f"/notebook/{nb.id}",
            json={"name": "New Name"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["name"] == "New Name"

    def test_update_notebook_by_other_user_returns_404(
        self,
        client: TestClient,
        test_user: User,
        other_auth_headers: dict[str, str],
        db_session: Session,
    ) -> None:
        nb = create_notebook(db_session, "Old Name", test_user)
        response = client.patch(
            f"/notebook/{nb.id}",
            json={"name": "Sneaky"},
            headers=other_auth_headers,
        )
        assert response.status_code == 404

    def test_update_notebook_by_viewer_returns_403(
        self,
        client: TestClient,
        test_user: User,
        other_user: User,
        other_auth_headers: dict[str, str],
        db_session: Session,
    ) -> None:
        nb = create_notebook(db_session, "Old Name", test_user)
        db_session.add(
            Entitlement(
                principal_id=other_user.uid,
                notebook_id=nb.id,
                role_name=RoleName.NOTEBOOK_VIEWER.value,
            ),
        )
        db_session.flush()

        response = client.patch(
            f"/notebook/{nb.id}",
            json={"name": "Sneaky"},
            headers=other_auth_headers,
        )
        assert response.status_code == 403


class TestDeleteNotebook:
    def test_delete_notebook(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
        test_user: User,
        db_session: Session,
    ) -> None:
        nb = create_notebook(db_session, "To Delete", test_user)
        response = client.delete(f"/notebook/{nb.id}", headers=auth_headers)
        assert response.status_code == 204

        response = client.get(f"/notebook/{nb.id}", headers=auth_headers)
        assert response.status_code == 404

    def test_delete_notebook_not_found(
        self,
        client: TestClient,
        auth_headers: dict[str, str],
    ) -> None:
        response = client.delete(f"/notebook/{uuid.uuid4()}", headers=auth_headers)
        assert response.status_code == 404
