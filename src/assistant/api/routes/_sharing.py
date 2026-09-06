"""Shared helpers for the share/entitlement endpoints in notebooks.py and notes.py."""

from __future__ import annotations

from fastapi import HTTPException

from assistant.models.schema import RoleName, SubjectType

_ROLES_BY_SUBJECT_TYPE: dict[SubjectType, frozenset[RoleName]] = {
    SubjectType.NOTEBOOK: frozenset(
        {RoleName.NOTEBOOK_OWNER, RoleName.NOTEBOOK_VIEWER, RoleName.NOTEBOOK_EDITOR},
    ),
    SubjectType.NOTE: frozenset(
        {RoleName.NOTE_OWNER, RoleName.NOTE_VIEWER, RoleName.NOTE_EDITOR},
    ),
}


def validate_role_for_subject_type(role: RoleName, subject_type: SubjectType) -> None:
    """Raise 422 if `role` doesn't belong to `subject_type`."""
    if role not in _ROLES_BY_SUBJECT_TYPE[subject_type]:
        detail = f"'{role.value}' is not a {subject_type.value} role"
        raise HTTPException(status_code=422, detail=detail)
