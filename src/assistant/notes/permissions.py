"""Permission evaluation — read-only: computes effective permissions and enforces them.

Roles and permissions are Python enums with no backing DB table (see the
Storage decision in `docs/plans/role_based_access_control.md`). This module
owns the single source of truth for role -> permission expansion.

An `Entitlement` grants a principal either a single `PermissionName` or a
whole `RoleName` (a fixed bundle) on exactly one subject (a Note or a
Notebook). Effective permissions on a subject are the union of every
entitlement the principal holds on it, with role grants expanded via
`ROLE_PERMISSIONS`.

Notebook and note permissions interact: `own_notes`/`view_notes` on a
notebook project onto every note it contains (see `note_permissions`), and
holding *any* entitlement on a note makes its parent notebook visible even
without a notebook-level grant (see `can_view_notebook`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import exists, select

from assistant.models.schema import (
    Entitlement,
    Note,
    Notebook,
    PermissionName,
    RoleName,
    SubjectType,
    User,
)
from assistant.notes.exceptions import (
    NotebookNotFoundError,
    NoteNotFoundError,
    PermissionDeniedError,
)

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session

ROLE_PERMISSIONS: dict[RoleName, frozenset[PermissionName]] = {
    RoleName.NOTEBOOK_OWNER: frozenset(
        {
            PermissionName.VIEW_NOTEBOOK,
            PermissionName.UPDATE_NOTEBOOK,
            PermissionName.DELETE_NOTEBOOK,
            PermissionName.CREATE_NOTES,
            PermissionName.LIST_NOTES,
            PermissionName.OWN_NOTES,
            PermissionName.DELETE_NOTES,
            PermissionName.VIEW_NOTES,
            PermissionName.SHARE_NOTEBOOK,
        },
    ),
    RoleName.NOTEBOOK_VIEWER: frozenset(
        {
            PermissionName.VIEW_NOTEBOOK,
            PermissionName.LIST_NOTES,
            PermissionName.VIEW_NOTES,
            PermissionName.SHARE_NOTEBOOK,
        },
    ),
    RoleName.NOTEBOOK_EDITOR: frozenset(
        {
            PermissionName.VIEW_NOTEBOOK,
            PermissionName.LIST_NOTES,
            PermissionName.VIEW_NOTES,
            PermissionName.SHARE_NOTEBOOK,
            PermissionName.CREATE_NOTES,
            PermissionName.OWN_NOTES,
            PermissionName.DELETE_NOTES,
            PermissionName.UPDATE_NOTEBOOK,
        },
    ),
    RoleName.NOTE_OWNER: frozenset(
        {
            PermissionName.VIEW_NOTE,
            PermissionName.UPDATE,
            PermissionName.DELETE_NOTE,
            PermissionName.SHARE_NOTE,
        },
    ),
    RoleName.NOTE_VIEWER: frozenset(
        {PermissionName.VIEW_NOTE, PermissionName.SHARE_NOTE},
    ),
    RoleName.NOTE_EDITOR: frozenset(
        {PermissionName.VIEW_NOTE, PermissionName.SHARE_NOTE, PermissionName.UPDATE},
    ),
}

_NOTE_OWNER_PERMISSIONS = ROLE_PERMISSIONS[RoleName.NOTE_OWNER]
_NOTE_VIEWER_PERMISSIONS = ROLE_PERMISSIONS[RoleName.NOTE_VIEWER]


def _granted_permission_names(
    session: Session,
    principal: User,
    *,
    note_id: uuid.UUID | None = None,
    notebook_id: uuid.UUID | None = None,
) -> set[PermissionName]:
    """Direct + role-expanded permission names a principal holds on one subject."""
    subject_filter = (
        Entitlement.note_id == note_id
        if note_id is not None
        else Entitlement.notebook_id == notebook_id
    )
    rows = session.scalars(
        select(Entitlement).where(
            Entitlement.principal_id == principal.uid,
            subject_filter,
        ),
    )
    names: set[PermissionName] = set()
    for entitlement in rows:
        if entitlement.permission_name is not None:
            names.add(PermissionName(entitlement.permission_name))
        else:
            assert entitlement.role_name is not None
            names |= ROLE_PERMISSIONS[RoleName(entitlement.role_name)]
    return names


def notebook_permissions(
    session: Session,
    principal: User,
    notebook_id: uuid.UUID,
) -> set[PermissionName]:
    """Direct + role-expanded permission names the principal holds on this notebook."""
    return _granted_permission_names(session, principal, notebook_id=notebook_id)


def note_permissions(
    session: Session,
    principal: User,
    note: Note,
) -> set[PermissionName]:
    """Effective permissions on a note: direct grants plus notebook-derived ones.

    `own_notes` on the parent notebook implies the full `note_owner` bundle;
    `view_notes` implies `{view_note, share_note}` (the `note_viewer` bundle).
    """
    direct = _granted_permission_names(session, principal, note_id=note.id)
    notebook_perms = notebook_permissions(session, principal, note.notebook_id)
    if PermissionName.OWN_NOTES in notebook_perms:
        direct |= _NOTE_OWNER_PERMISSIONS
    if PermissionName.VIEW_NOTES in notebook_perms:
        direct |= _NOTE_VIEWER_PERMISSIONS
    return direct


def can_view_notebook(
    session: Session,
    principal: User,
    notebook_id: uuid.UUID,
) -> bool:
    """True if the principal can see the notebook.

    Either directly (any notebook-level entitlement granting VIEW_NOTEBOOK),
    or because they hold any entitlement at all on a note inside it.
    """
    perms = notebook_permissions(session, principal, notebook_id)
    if PermissionName.VIEW_NOTEBOOK in perms:
        return True
    stmt = select(
        exists().where(
            Entitlement.principal_id == principal.uid,
            Entitlement.note_id == Note.id,
            Note.notebook_id == notebook_id,
        ),
    )
    return bool(session.scalar(stmt))


def require_notebook_access(
    session: Session,
    notebook_id: uuid.UUID,
    principal: User,
    permission: PermissionName,
) -> Notebook:
    """Return the Notebook if visible and `permission` is held; else raise.

    404-shaped `NotebookNotFoundError` if the caller cannot even view the
    notebook; `PermissionDeniedError` (403) if visible but lacking
    `permission`.
    """
    if not can_view_notebook(session, principal, notebook_id):
        raise NotebookNotFoundError(str(notebook_id))
    notebook = session.get(Notebook, notebook_id)
    if notebook is None:
        raise NotebookNotFoundError(str(notebook_id))
    if permission not in notebook_permissions(session, principal, notebook_id):
        raise PermissionDeniedError(permission, SubjectType.NOTEBOOK, notebook_id)
    return notebook


def require_note_access(
    session: Session,
    note_id: uuid.UUID,
    principal: User,
    permission: PermissionName,
) -> Note:
    """Return the Note if visible and `permission` is held; else raise.

    404-shaped `NoteNotFoundError` if the caller lacks even VIEW_NOTE;
    `PermissionDeniedError` (403) if visible but lacking `permission`.
    """
    note = session.get(Note, note_id)
    if note is None:
        raise NoteNotFoundError(str(note_id))
    perms = note_permissions(session, principal, note)
    if PermissionName.VIEW_NOTE not in perms:
        raise NoteNotFoundError(str(note_id))
    if permission not in perms:
        raise PermissionDeniedError(permission, SubjectType.NOTE, note_id)
    return note


def require_note_delete_access(
    session: Session,
    note_id: uuid.UUID,
    principal: User,
) -> Note:
    """Deleting a note is allowed via DELETE_NOTE, or notebook DELETE_NOTES/OWN_NOTES."""
    note = session.get(Note, note_id)
    if note is None:
        raise NoteNotFoundError(str(note_id))
    perms = note_permissions(session, principal, note)
    if PermissionName.VIEW_NOTE not in perms:
        raise NoteNotFoundError(str(note_id))
    notebook_perms = notebook_permissions(session, principal, note.notebook_id)
    if (
        PermissionName.DELETE_NOTE not in perms
        and PermissionName.DELETE_NOTES not in notebook_perms
        and PermissionName.OWN_NOTES not in notebook_perms
    ):
        raise PermissionDeniedError(PermissionName.DELETE_NOTE, SubjectType.NOTE, note_id)
    return note


__all__ = [
    "ROLE_PERMISSIONS",
    "can_view_notebook",
    "note_permissions",
    "notebook_permissions",
    "require_note_access",
    "require_note_delete_access",
    "require_notebook_access",
]
