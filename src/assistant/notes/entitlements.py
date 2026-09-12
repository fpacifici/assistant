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

from assistant.config import Config
from assistant.email.service import Email, send_best_effort_email
from assistant.email.templates import SHARE_NOTIFICATION_EMAIL
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
from assistant.urls import note_url, notebook_url

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
) -> tuple[Entitlement, bool]:
    """Grant `role_name` on the given subject to the user with `grantee_email`.

    Returns (entitlement, created) — created is False when an identical
    grant already existed (the idempotent case), which callers use to
    decide whether to send a share notification (only on an actual new
    grant, per spec).

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
        return existing, False

    entitlement = Entitlement(
        principal_id=grantee.uid,
        note_id=note_id,
        notebook_id=notebook_id,
        role_name=role_name.value,
    )
    session.add(entitlement)
    session.flush()
    return entitlement, True


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


def send_share_notification_email(  # noqa: PLR0913
    *,
    granter_name: str,
    grantee_email: str,
    role: RoleName,
    subject_type: SubjectType,
    notebook_id: uuid.UUID,
    note_id: uuid.UUID | None,
) -> None:
    """Best-effort notification for a new share grant.

    Scheduled via FastAPI `BackgroundTasks` from the share route handlers
    (this module has no access to `BackgroundTasks` itself — that stays a
    route-layer concern) specifically so a failure here can't affect the
    share API response.
    """
    config = Config()
    url = (
        note_url(notebook_id, note_id, config)
        if note_id is not None
        else notebook_url(notebook_id, config)
    )

    email = Email(
        recipient=grantee_email,
        subject="Something was shared with you on Assistant",
        template=SHARE_NOTIFICATION_EMAIL,
        values={
            "granter_name": granter_name,
            "subject_type": subject_type.value,
            "role": role.value,
            "url": url,
        },
    )
    send_best_effort_email(email, context="share notification")


__all__ = [
    "grant_entitlement",
    "list_entitlements",
    "revoke_entitlement",
    "send_share_notification_email",
]
