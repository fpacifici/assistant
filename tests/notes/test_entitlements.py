"""Tests for the entitlement write-side: grant/revoke/list."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from assistant.models.schema import Entitlement, Notebook, RoleName, User
from assistant.notes.entitlements import (
    grant_entitlement,
    list_entitlements,
    revoke_entitlement,
)
from assistant.notes.exceptions import (
    NotebookNotFoundError,
    PermissionDeniedError,
    UserNotFoundError,
)
from assistant.notes.service import create_note, create_notebook


def _make_user(session: Session, email: str = "u@test.com") -> User:
    user = User(email=email, firstname="A", lastname="B")
    session.add(user)
    session.flush()
    return user


def _make_notebook(session: Session, owner: User, name: str = "NB") -> Notebook:
    return create_notebook(session, name, owner)


# -----------------------------------------------------------------------
# grant_entitlement — notebooks
# -----------------------------------------------------------------------


def test_owner_can_grant_up_to_full_ownership(db_session: Session) -> None:
    owner = _make_user(db_session, "owner@test.com")
    grantee = _make_user(db_session, "grantee@test.com")
    nb = _make_notebook(db_session, owner)

    entitlement, _ = grant_entitlement(
        db_session,
        owner,
        notebook_id=nb.id,
        grantee_email=grantee.email,
        role_name=RoleName.NOTEBOOK_OWNER,
    )
    assert entitlement.principal_id == grantee.uid
    assert entitlement.role_name == RoleName.NOTEBOOK_OWNER.value


def test_granter_within_own_permission_level_succeeds(db_session: Session) -> None:
    owner = _make_user(db_session, "owner@test.com")
    editor = _make_user(db_session, "editor@test.com")
    grantee = _make_user(db_session, "grantee@test.com")
    nb = _make_notebook(db_session, owner)
    grant_entitlement(
        db_session,
        owner,
        notebook_id=nb.id,
        grantee_email=editor.email,
        role_name=RoleName.NOTEBOOK_EDITOR,
    )

    entitlement, _ = grant_entitlement(
        db_session,
        editor,
        notebook_id=nb.id,
        grantee_email=grantee.email,
        role_name=RoleName.NOTEBOOK_VIEWER,
    )
    assert entitlement.role_name == RoleName.NOTEBOOK_VIEWER.value


def test_granter_cannot_exceed_own_permission_level(db_session: Session) -> None:
    owner = _make_user(db_session, "owner@test.com")
    editor = _make_user(db_session, "editor@test.com")
    grantee = _make_user(db_session, "grantee@test.com")
    nb = _make_notebook(db_session, owner)
    grant_entitlement(
        db_session,
        owner,
        notebook_id=nb.id,
        grantee_email=editor.email,
        role_name=RoleName.NOTEBOOK_EDITOR,
    )

    with pytest.raises(PermissionDeniedError):
        grant_entitlement(
            db_session,
            editor,
            notebook_id=nb.id,
            grantee_email=grantee.email,
            role_name=RoleName.NOTEBOOK_OWNER,
        )


def test_note_editor_cannot_grant_note_owner(db_session: Session) -> None:
    owner = _make_user(db_session, "owner@test.com")
    editor = _make_user(db_session, "editor@test.com")
    grantee = _make_user(db_session, "grantee@test.com")
    nb = _make_notebook(db_session, owner)
    note = create_note(db_session, nb.id, owner, "Note")
    grant_entitlement(
        db_session,
        owner,
        note_id=note.id,
        grantee_email=editor.email,
        role_name=RoleName.NOTE_EDITOR,
    )

    with pytest.raises(PermissionDeniedError):
        grant_entitlement(
            db_session,
            editor,
            note_id=note.id,
            grantee_email=grantee.email,
            role_name=RoleName.NOTE_OWNER,
        )


def test_grant_unregistered_email_raises_user_not_found(db_session: Session) -> None:
    owner = _make_user(db_session, "owner@test.com")
    nb = _make_notebook(db_session, owner)

    with pytest.raises(UserNotFoundError):
        grant_entitlement(
            db_session,
            owner,
            notebook_id=nb.id,
            grantee_email="nobody@test.com",
            role_name=RoleName.NOTEBOOK_VIEWER,
        )


def test_granting_without_view_access_raises_not_found(db_session: Session) -> None:
    owner = _make_user(db_session, "owner@test.com")
    stranger = _make_user(db_session, "stranger@test.com")
    grantee = _make_user(db_session, "grantee@test.com")
    nb = _make_notebook(db_session, owner)

    with pytest.raises(NotebookNotFoundError):
        grant_entitlement(
            db_session,
            stranger,
            notebook_id=nb.id,
            grantee_email=grantee.email,
            role_name=RoleName.NOTEBOOK_VIEWER,
        )


def test_grant_entitlement_reports_created_true_on_fresh_grant(
    db_session: Session,
) -> None:
    owner = _make_user(db_session, "owner@test.com")
    grantee = _make_user(db_session, "grantee@test.com")
    nb = _make_notebook(db_session, owner)

    _, created = grant_entitlement(
        db_session,
        owner,
        notebook_id=nb.id,
        grantee_email=grantee.email,
        role_name=RoleName.NOTEBOOK_VIEWER,
    )
    assert created is True


def test_grant_entitlement_reports_created_false_on_repeat_grant(
    db_session: Session,
) -> None:
    owner = _make_user(db_session, "owner@test.com")
    grantee = _make_user(db_session, "grantee@test.com")
    nb = _make_notebook(db_session, owner)

    grant_entitlement(
        db_session,
        owner,
        notebook_id=nb.id,
        grantee_email=grantee.email,
        role_name=RoleName.NOTEBOOK_VIEWER,
    )
    _, created = grant_entitlement(
        db_session,
        owner,
        notebook_id=nb.id,
        grantee_email=grantee.email,
        role_name=RoleName.NOTEBOOK_VIEWER,
    )
    assert created is False


def test_granting_same_role_twice_is_idempotent(db_session: Session) -> None:
    owner = _make_user(db_session, "owner@test.com")
    grantee = _make_user(db_session, "grantee@test.com")
    nb = _make_notebook(db_session, owner)

    first, _ = grant_entitlement(
        db_session,
        owner,
        notebook_id=nb.id,
        grantee_email=grantee.email,
        role_name=RoleName.NOTEBOOK_VIEWER,
    )
    second, _ = grant_entitlement(
        db_session,
        owner,
        notebook_id=nb.id,
        grantee_email=grantee.email,
        role_name=RoleName.NOTEBOOK_VIEWER,
    )
    assert first.id == second.id
    count = (
        db_session.query(Entitlement)
        .filter(
            Entitlement.notebook_id == nb.id,
            Entitlement.principal_id == grantee.uid,
            Entitlement.role_name == RoleName.NOTEBOOK_VIEWER.value,
        )
        .count()
    )
    assert count == 1


# -----------------------------------------------------------------------
# revoke_entitlement
# -----------------------------------------------------------------------


def test_revoke_by_sufficiently_privileged_user_succeeds(db_session: Session) -> None:
    owner = _make_user(db_session, "owner@test.com")
    grantee = _make_user(db_session, "grantee@test.com")
    nb = _make_notebook(db_session, owner)
    entitlement, _ = grant_entitlement(
        db_session,
        owner,
        notebook_id=nb.id,
        grantee_email=grantee.email,
        role_name=RoleName.NOTEBOOK_VIEWER,
    )

    revoke_entitlement(db_session, owner, entitlement.id, notebook_id=nb.id)

    assert db_session.get(Entitlement, entitlement.id) is None


def test_revoke_by_insufficiently_privileged_user_fails(db_session: Session) -> None:
    owner = _make_user(db_session, "owner@test.com")
    viewer = _make_user(db_session, "viewer@test.com")
    grantee = _make_user(db_session, "grantee@test.com")
    nb = _make_notebook(db_session, owner)
    grant_entitlement(
        db_session,
        owner,
        notebook_id=nb.id,
        grantee_email=viewer.email,
        role_name=RoleName.NOTEBOOK_VIEWER,
    )
    other_entitlement, _ = grant_entitlement(
        db_session,
        owner,
        notebook_id=nb.id,
        grantee_email=grantee.email,
        role_name=RoleName.NOTEBOOK_EDITOR,
    )

    with pytest.raises(PermissionDeniedError):
        revoke_entitlement(
            db_session,
            viewer,
            other_entitlement.id,
            notebook_id=nb.id,
        )


def test_revoke_absent_entitlement_is_noop(db_session: Session) -> None:
    owner = _make_user(db_session, "owner@test.com")
    nb = _make_notebook(db_session, owner)

    revoke_entitlement(db_session, owner, uuid.uuid4(), notebook_id=nb.id)


# -----------------------------------------------------------------------
# list_entitlements
# -----------------------------------------------------------------------


def test_list_entitlements_requires_share_permission(db_session: Session) -> None:
    owner = _make_user(db_session, "owner@test.com")
    stranger = _make_user(db_session, "stranger@test.com")
    nb = _make_notebook(db_session, owner)

    with pytest.raises(NotebookNotFoundError):
        list_entitlements(db_session, stranger, notebook_id=nb.id)


def test_list_entitlements_returns_all_grants_on_subject(db_session: Session) -> None:
    owner = _make_user(db_session, "owner@test.com")
    viewer = _make_user(db_session, "viewer@test.com")
    nb = _make_notebook(db_session, owner)
    grant_entitlement(
        db_session,
        owner,
        notebook_id=nb.id,
        grantee_email=viewer.email,
        role_name=RoleName.NOTEBOOK_VIEWER,
    )

    entitlements = list_entitlements(db_session, owner, notebook_id=nb.id)
    # owner's own auto-created entitlement + the viewer grant
    assert len(entitlements) == 2
