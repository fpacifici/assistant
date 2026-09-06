"""Tests for the sharing (entitlement) HTTP endpoints, notebooks and notes."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from assistant.models.schema import Entitlement, RoleName
from assistant.notes.service import create_note, create_notebook
from assistant.notes.user_service import create_user

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from assistant.models.schema import User

# ---------------------------------------------------------------------------
# Notebook sharing
# ---------------------------------------------------------------------------


def test_share_notebook_by_email_succeeds(
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    other_user: User,
    db_session: Session,
) -> None:
    nb = create_notebook(db_session, "NB", test_user)

    response = client.post(
        f"/notebook/{nb.id}/share",
        json={"email": other_user.email, "role": "notebook_viewer"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["principal_email"] == other_user.email
    assert body["role"] == "notebook_viewer"


def test_grantee_gets_access_on_next_request(  # noqa: PLR0913
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    other_user: User,
    other_auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    nb = create_notebook(db_session, "NB", test_user)
    client.post(
        f"/notebook/{nb.id}/share",
        json={"email": other_user.email, "role": "notebook_viewer"},
        headers=auth_headers,
    )

    response = client.get(f"/notebook/{nb.id}", headers=other_auth_headers)
    assert response.status_code == 200


def test_share_notebook_unknown_email_returns_404(
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    db_session: Session,
) -> None:
    nb = create_notebook(db_session, "NB", test_user)

    response = client.post(
        f"/notebook/{nb.id}/share",
        json={"email": "nobody@test.com", "role": "notebook_viewer"},
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_share_notebook_exceeding_granter_level_returns_403(
    client: TestClient,
    test_user: User,
    other_user: User,
    other_auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    grantee_email = "third@test.com"
    third = create_user(db_session, grantee_email, "Third", "User")
    nb = create_notebook(db_session, "NB", test_user)
    db_session.add(
        Entitlement(
            principal_id=other_user.uid,
            notebook_id=nb.id,
            role_name=RoleName.NOTEBOOK_VIEWER.value,
        ),
    )
    db_session.flush()

    response = client.post(
        f"/notebook/{nb.id}/share",
        json={"email": third.email, "role": "notebook_owner"},
        headers=other_auth_headers,
    )
    assert response.status_code == 403


def test_share_notebook_with_note_role_returns_422(
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    other_user: User,
    db_session: Session,
) -> None:
    nb = create_notebook(db_session, "NB", test_user)

    response = client.post(
        f"/notebook/{nb.id}/share",
        json={"email": other_user.email, "role": "note_viewer"},
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_revoke_notebook_share_removes_access(  # noqa: PLR0913
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    other_user: User,
    other_auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    nb = create_notebook(db_session, "NB", test_user)
    share_response = client.post(
        f"/notebook/{nb.id}/share",
        json={"email": other_user.email, "role": "notebook_viewer"},
        headers=auth_headers,
    )
    entitlement_id = share_response.json()["id"]

    revoke_response = client.delete(
        f"/notebook/{nb.id}/share/{entitlement_id}",
        headers=auth_headers,
    )
    assert revoke_response.status_code == 204

    response = client.get(f"/notebook/{nb.id}", headers=other_auth_headers)
    assert response.status_code == 404


def test_revoke_notebook_share_by_insufficient_user_returns_403(  # noqa: PLR0913
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    other_user: User,
    other_auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    editor = create_user(db_session, "editor@test.com", "E", "U")
    nb = create_notebook(db_session, "NB", test_user)
    client.post(
        f"/notebook/{nb.id}/share",
        json={"email": other_user.email, "role": "notebook_viewer"},
        headers=auth_headers,
    )
    editor_share = client.post(
        f"/notebook/{nb.id}/share",
        json={"email": editor.email, "role": "notebook_editor"},
        headers=auth_headers,
    )
    entitlement_id = editor_share.json()["id"]

    response = client.delete(
        f"/notebook/{nb.id}/share/{entitlement_id}",
        headers=other_auth_headers,
    )
    assert response.status_code == 403


def test_list_notebook_shares_requires_share_permission(
    client: TestClient,
    test_user: User,
    other_auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    nb = create_notebook(db_session, "NB", test_user)

    response = client.get(f"/notebook/{nb.id}/share", headers=other_auth_headers)
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Note sharing
# ---------------------------------------------------------------------------


def test_share_note_by_email_succeeds(
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    other_user: User,
    db_session: Session,
) -> None:
    nb = create_notebook(db_session, "NB", test_user)
    note = create_note(db_session, nb.id, test_user, "N")

    response = client.post(
        f"/notebook/{nb.id}/note/{note.id}/share",
        json={"email": other_user.email, "role": "note_viewer"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert response.json()["role"] == "note_viewer"


def test_share_note_with_notebook_role_returns_422(
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    other_user: User,
    db_session: Session,
) -> None:
    nb = create_notebook(db_session, "NB", test_user)
    note = create_note(db_session, nb.id, test_user, "N")

    response = client.post(
        f"/notebook/{nb.id}/note/{note.id}/share",
        json={"email": other_user.email, "role": "notebook_viewer"},
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_revoke_note_share_removes_access(  # noqa: PLR0913
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    other_user: User,
    other_auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    nb = create_notebook(db_session, "NB", test_user)
    note = create_note(db_session, nb.id, test_user, "N")
    share_response = client.post(
        f"/notebook/{nb.id}/note/{note.id}/share",
        json={"email": other_user.email, "role": "note_viewer"},
        headers=auth_headers,
    )
    entitlement_id = share_response.json()["id"]

    revoke_response = client.delete(
        f"/notebook/{nb.id}/note/{note.id}/share/{entitlement_id}",
        headers=auth_headers,
    )
    assert revoke_response.status_code == 204

    response = client.get(
        f"/notebook/{nb.id}/note/{note.id}",
        headers=other_auth_headers,
    )
    assert response.status_code == 404


def test_share_note_by_grantee_without_share_note_returns_404(
    client: TestClient,
    test_user: User,
    other_auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    nb = create_notebook(db_session, "NB", test_user)
    note = create_note(db_session, nb.id, test_user, "N")

    response = client.post(
        f"/notebook/{nb.id}/note/{note.id}/share",
        json={"email": "someone@test.com", "role": "note_viewer"},
        headers=other_auth_headers,
    )
    assert response.status_code == 404


def test_share_note_unknown_id_returns_404(
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    db_session: Session,
) -> None:
    nb = create_notebook(db_session, "NB", test_user)

    response = client.post(
        f"/notebook/{nb.id}/note/{uuid.uuid4()}/share",
        json={"email": "someone@test.com", "role": "note_viewer"},
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_list_note_shares_requires_share_permission(
    client: TestClient,
    test_user: User,
    other_auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    nb = create_notebook(db_session, "NB", test_user)
    note = create_note(db_session, nb.id, test_user, "N")

    response = client.get(
        f"/notebook/{nb.id}/note/{note.id}/share",
        headers=other_auth_headers,
    )
    assert response.status_code == 404


def test_revoke_note_share_by_insufficient_user_returns_403(  # noqa: PLR0913
    client: TestClient,
    auth_headers: dict[str, str],
    test_user: User,
    other_user: User,
    other_auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    editor = create_user(db_session, "note-editor@test.com", "E", "U")
    nb = create_notebook(db_session, "NB", test_user)
    note = create_note(db_session, nb.id, test_user, "N")
    client.post(
        f"/notebook/{nb.id}/note/{note.id}/share",
        json={"email": other_user.email, "role": "note_viewer"},
        headers=auth_headers,
    )
    editor_share = client.post(
        f"/notebook/{nb.id}/note/{note.id}/share",
        json={"email": editor.email, "role": "note_editor"},
        headers=auth_headers,
    )
    entitlement_id = editor_share.json()["id"]

    response = client.delete(
        f"/notebook/{nb.id}/note/{note.id}/share/{entitlement_id}",
        headers=other_auth_headers,
    )
    assert response.status_code == 403
