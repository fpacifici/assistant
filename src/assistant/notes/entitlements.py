"""Entitlement write-side — grant/revoke/list, bounded by the escalation rule.

A granter/revoker/viewer must hold `share_note`/`share_notebook` on the
subject, and may never grant or revoke more than their own current
effective permission level on that subject (checked by expanding the role
being granted/revoked via `ROLE_PERMISSIONS` and verifying it is a subset of
the actor's own effective permissions).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from assistant.models.schema import (
    Entitlement,
    PermissionName,
    RoleName,
    SubjectType,
    User,
)
from assistant.notes.exceptions import PermissionDeniedError
from assistant.notes.permissions import (
    ROLE_PERMISSIONS,
    note_permissions,
    notebook_permissions,
    require_note_access,
    require_notebook_access,
)
from assistant.notes.user_service import get_user_by_email

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session


def _require_share_and_bound(
    session: Session,
    actor: User,
    role_name: RoleName,
    *,
    note_id: uuid.UUID | None = None,
    notebook_id: uuid.UUID | None = None,
) -> set[PermissionName]:
    """Verify actor can share the subject and that role_name is within their reach.

    Returns the actor's own effective permission set on the subject (reused
    by callers to avoid recomputing it).
    """
    if note_id is not None:
        note = require_note_access(session, note_id, actor, PermissionName.SHARE_NOTE)
        actor_perms = note_permissions(session, actor, note)
        subject_type = SubjectType.NOTE
        subject_id = note_id
    else:
        assert notebook_id is not None
        require_notebook_access(
            session,
            notebook_id,
            actor,
            PermissionName.SHARE_NOTEBOOK,
        )
        actor_perms = notebook_permissions(session, actor, notebook_id)
        subject_type = SubjectType.NOTEBOOK
        subject_id = notebook_id

    role_bundle = ROLE_PERMISSIONS[role_name]
    if not role_bundle.issubset(actor_perms):
        raise PermissionDeniedError(
            next(iter(role_bundle - actor_perms)),
            subject_type,
            subject_id,
        )
    return actor_perms


def grant_entitlement(  # noqa: PLR0913
    session: Session,
    granter: User,
    *,
    note_id: uuid.UUID | None = None,
    notebook_id: uuid.UUID | None = None,
    grantee_email: str,
    role_name: RoleName,
) -> Entitlement:
    """Grant `role_name` on the given subject to the user with `grantee_email`.

    Raises `UserNotFoundError` if no user has that email. Raises
    `PermissionDeniedError` if `granter` lacks `share_note`/
    `share_notebook` on the subject, or if `role_name`'s permission bundle
    is not a subset of the granter's own effective permissions there.

    Idempotent: granting the same (grantee, subject, role) twice returns the
    existing row rather than duplicating it. This is checked in Python, not
    relied on at the DB level — `uq_entitlement_no_duplicate_grant` includes
    the nullable `permission_name`/`role_name` columns, and most backends
    (including SQLite and Postgres) treat NULL as distinct from NULL in a
    unique constraint, so two role-only grants would not collide there.
    """
    _require_share_and_bound(
        session,
        granter,
        role_name,
        note_id=note_id,
        notebook_id=notebook_id,
    )
    grantee = get_user_by_email(session, grantee_email)

    existing = session.scalar(
        select(Entitlement).where(
            Entitlement.principal_id == grantee.uid,
            Entitlement.note_id == note_id,
            Entitlement.notebook_id == notebook_id,
            Entitlement.role_name == role_name.value,
        ),
    )
    if existing is not None:
        return existing

    entitlement = Entitlement(
        principal_id=grantee.uid,
        note_id=note_id,
        notebook_id=notebook_id,
        role_name=role_name.value,
    )
    session.add(entitlement)
    session.flush()
    return entitlement


def revoke_entitlement(
    session: Session,
    revoker: User,
    entitlement_id: uuid.UUID,
    *,
    note_id: uuid.UUID | None = None,
    notebook_id: uuid.UUID | None = None,
) -> None:
    """Revoke an entitlement. Idempotent — revoking an absent one is a no-op.

    The revoker must hold `share_note`/`share_notebook` on the subject, and
    the entitlement being removed must not exceed the revoker's own
    permission level on that subject.
    """
    entitlement = session.get(Entitlement, entitlement_id)
    if entitlement is None:
        return

    role_name = RoleName(entitlement.role_name) if entitlement.role_name else None
    if role_name is not None:
        _require_share_and_bound(
            session,
            revoker,
            role_name,
            note_id=note_id,
            notebook_id=notebook_id,
        )
    else:
        # Permission-only grants: bound by treating the single permission as
        # a one-permission "role" for the escalation check.
        permission = PermissionName(entitlement.permission_name)
        if note_id is not None:
            note = require_note_access(
                session,
                note_id,
                revoker,
                PermissionName.SHARE_NOTE,
            )
            actor_perms = note_permissions(session, revoker, note)
            subject_type = SubjectType.NOTE
            subject_id = note_id
        else:
            assert notebook_id is not None
            require_notebook_access(
                session,
                notebook_id,
                revoker,
                PermissionName.SHARE_NOTEBOOK,
            )
            actor_perms = notebook_permissions(session, revoker, notebook_id)
            subject_type = SubjectType.NOTEBOOK
            subject_id = notebook_id
        if permission not in actor_perms:
            raise PermissionDeniedError(permission, subject_type, subject_id)

    session.delete(entitlement)
    session.flush()


def list_entitlements(
    session: Session,
    viewer: User,
    *,
    note_id: uuid.UUID | None = None,
    notebook_id: uuid.UUID | None = None,
) -> list[Entitlement]:
    """List entitlements on a subject. Requires share_note/share_notebook on it."""
    if note_id is not None:
        require_note_access(session, note_id, viewer, PermissionName.SHARE_NOTE)
        stmt = select(Entitlement).where(Entitlement.note_id == note_id)
    else:
        assert notebook_id is not None
        require_notebook_access(
            session,
            notebook_id,
            viewer,
            PermissionName.SHARE_NOTEBOOK,
        )
        stmt = select(Entitlement).where(Entitlement.notebook_id == notebook_id)
    return list(session.scalars(stmt))


__all__ = ["grant_entitlement", "list_entitlements", "revoke_entitlement"]
