"""Tests for the pure permission-evaluation seam in `notes/permissions.py`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from assistant.models.schema import (
    Entitlement,
    Note,
    Notebook,
    PermissionName,
    RoleName,
    User,
)
from assistant.notes.exceptions import (
    NotebookNotFoundError,
    NoteNotFoundError,
    PermissionDeniedError,
)
from assistant.notes.permissions import (
    can_view_notebook,
    note_permissions,
    notebook_permissions,
    require_note_access,
    require_notebook_access,
)


def _make_user(session: Session, email: str = "u@test.com") -> User:
    user = User(email=email, firstname="A", lastname="B")
    session.add(user)
    session.flush()
    return user


def _make_notebook(session: Session, owner: User, name: str = "NB") -> Notebook:
    notebook = Notebook(name=name, owner_id=owner.uid)
    session.add(notebook)
    session.flush()
    return notebook


def _make_note(
    session: Session,
    notebook: Notebook,
    owner: User,
    title: str = "N",
) -> Note:
    note = Note(
        notebook_id=notebook.id,
        owner_id=owner.uid,
        title=title,
        update_timestamp=datetime.now(UTC),
    )
    session.add(note)
    session.flush()
    return note


def _grant(  # noqa: PLR0913
    session: Session,
    principal: User,
    *,
    note_id: uuid.UUID | None = None,
    notebook_id: uuid.UUID | None = None,
    permission_name: PermissionName | None = None,
    role_name: RoleName | None = None,
) -> Entitlement:
    entitlement = Entitlement(
        principal_id=principal.uid,
        note_id=note_id,
        notebook_id=notebook_id,
        permission_name=permission_name.value if permission_name else None,
        role_name=role_name.value if role_name else None,
    )
    session.add(entitlement)
    session.flush()
    return entitlement


# -----------------------------------------------------------------------
# notebook_permissions / note_permissions
# -----------------------------------------------------------------------


def test_direct_permission_grant_visible(db_session: Session) -> None:
    owner = _make_user(db_session, "owner@test.com")
    other = _make_user(db_session, "other@test.com")
    nb = _make_notebook(db_session, owner)
    _grant(
        db_session,
        other,
        notebook_id=nb.id,
        permission_name=PermissionName.VIEW_NOTEBOOK,
    )

    perms = notebook_permissions(db_session, other, nb.id)
    assert perms == {PermissionName.VIEW_NOTEBOOK}


def test_role_grant_expands_to_bundle(db_session: Session) -> None:
    owner = _make_user(db_session, "owner@test.com")
    other = _make_user(db_session, "other@test.com")
    nb = _make_notebook(db_session, owner)
    _grant(db_session, other, notebook_id=nb.id, role_name=RoleName.NOTEBOOK_VIEWER)

    perms = notebook_permissions(db_session, other, nb.id)
    assert perms == {
        PermissionName.VIEW_NOTEBOOK,
        PermissionName.LIST_NOTES,
        PermissionName.VIEW_NOTES,
        PermissionName.SHARE_NOTEBOOK,
    }


def test_own_notes_implies_full_note_owner_set(db_session: Session) -> None:
    owner = _make_user(db_session, "owner@test.com")
    other = _make_user(db_session, "other@test.com")
    nb = _make_notebook(db_session, owner)
    note = _make_note(db_session, nb, owner)
    _grant(db_session, other, notebook_id=nb.id, permission_name=PermissionName.OWN_NOTES)

    perms = note_permissions(db_session, other, note)
    assert perms == {
        PermissionName.VIEW_NOTE,
        PermissionName.UPDATE,
        PermissionName.DELETE_NOTE,
        PermissionName.SHARE_NOTE,
    }


def test_view_notes_implies_only_view_and_share(db_session: Session) -> None:
    owner = _make_user(db_session, "owner@test.com")
    other = _make_user(db_session, "other@test.com")
    nb = _make_notebook(db_session, owner)
    note = _make_note(db_session, nb, owner)
    _grant(
        db_session,
        other,
        notebook_id=nb.id,
        permission_name=PermissionName.VIEW_NOTES,
    )

    perms = note_permissions(db_session, other, note)
    assert perms == {PermissionName.VIEW_NOTE, PermissionName.SHARE_NOTE}
    assert PermissionName.UPDATE not in perms
    assert PermissionName.DELETE_NOTE not in perms


def test_list_notes_alone_does_not_imply_view_notes(db_session: Session) -> None:
    owner = _make_user(db_session, "owner@test.com")
    other = _make_user(db_session, "other@test.com")
    nb = _make_notebook(db_session, owner)
    note = _make_note(db_session, nb, owner)
    _grant(
        db_session,
        other,
        notebook_id=nb.id,
        permission_name=PermissionName.LIST_NOTES,
    )

    perms = note_permissions(db_session, other, note)
    assert perms == set()


# -----------------------------------------------------------------------
# can_view_notebook
# -----------------------------------------------------------------------


def test_note_only_entitlement_makes_notebook_visible(db_session: Session) -> None:
    owner = _make_user(db_session, "owner@test.com")
    other = _make_user(db_session, "other@test.com")
    nb = _make_notebook(db_session, owner)
    note = _make_note(db_session, nb, owner)
    _grant(db_session, other, note_id=note.id, role_name=RoleName.NOTE_VIEWER)

    assert can_view_notebook(db_session, other, nb.id) is True
    perms = notebook_permissions(db_session, other, nb.id)
    assert PermissionName.VIEW_NOTEBOOK not in perms


def test_no_entitlement_at_all_notebook_not_visible(db_session: Session) -> None:
    owner = _make_user(db_session, "owner@test.com")
    other = _make_user(db_session, "other@test.com")
    nb = _make_notebook(db_session, owner)

    assert can_view_notebook(db_session, other, nb.id) is False


# -----------------------------------------------------------------------
# require_note_access / require_notebook_access
# -----------------------------------------------------------------------


def test_require_note_access_raises_not_found_without_view(db_session: Session) -> None:
    owner = _make_user(db_session, "owner@test.com")
    other = _make_user(db_session, "other@test.com")
    nb = _make_notebook(db_session, owner)
    note = _make_note(db_session, nb, owner)

    with pytest.raises(NoteNotFoundError):
        require_note_access(db_session, note.id, other, PermissionName.VIEW_NOTE)


def test_require_note_access_raises_permission_denied_when_visible_but_lacking(
    db_session: Session,
) -> None:
    owner = _make_user(db_session, "owner@test.com")
    other = _make_user(db_session, "other@test.com")
    nb = _make_notebook(db_session, owner)
    note = _make_note(db_session, nb, owner)
    _grant(db_session, other, note_id=note.id, role_name=RoleName.NOTE_VIEWER)

    with pytest.raises(PermissionDeniedError):
        require_note_access(db_session, note.id, other, PermissionName.UPDATE)


def test_require_notebook_access_raises_not_found_without_view(
    db_session: Session,
) -> None:
    owner = _make_user(db_session, "owner@test.com")
    other = _make_user(db_session, "other@test.com")
    nb = _make_notebook(db_session, owner)

    with pytest.raises(NotebookNotFoundError):
        require_notebook_access(
            db_session,
            nb.id,
            other,
            PermissionName.VIEW_NOTEBOOK,
        )


def test_require_notebook_access_raises_permission_denied_when_visible_but_lacking(
    db_session: Session,
) -> None:
    owner = _make_user(db_session, "owner@test.com")
    other = _make_user(db_session, "other@test.com")
    nb = _make_notebook(db_session, owner)
    _grant(db_session, other, notebook_id=nb.id, role_name=RoleName.NOTEBOOK_VIEWER)

    with pytest.raises(PermissionDeniedError):
        require_notebook_access(
            db_session,
            nb.id,
            other,
            PermissionName.DELETE_NOTEBOOK,
        )


def test_two_users_entitlements_do_not_leak(db_session: Session) -> None:
    owner = _make_user(db_session, "owner@test.com")
    alice = _make_user(db_session, "alice@test.com")
    bob = _make_user(db_session, "bob@test.com")
    nb = _make_notebook(db_session, owner)
    _grant(db_session, alice, notebook_id=nb.id, role_name=RoleName.NOTEBOOK_VIEWER)

    assert notebook_permissions(db_session, bob, nb.id) == set()
    assert can_view_notebook(db_session, bob, nb.id) is False
