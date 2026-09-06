"""Notes service exceptions."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid

    from assistant.models.schema import PermissionName, SubjectType


class NotesServiceError(Exception):
    """Base exception for the notes service."""


class UserNotFoundError(NotesServiceError):
    """Raised when a user is not found."""


class NotebookNotFoundError(NotesServiceError):
    """Raised when a notebook is not found."""


class DuplicateNotebookNameError(NotesServiceError):
    """Raised when creating a notebook whose name already exists."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"Notebook name already exists: {name}")


class NoteNotFoundError(NotesServiceError):
    """Raised when a note is not found."""


class NodeNotFoundError(NotesServiceError):
    """Raised when a node is not found."""


class InvalidNodeTypeError(NotesServiceError):
    """Raised when an operation is applied to the wrong node type."""


class InvalidBlockTypeError(NotesServiceError):
    """Raised when an invalid markdown block type is provided."""


class PermissionDeniedError(NotesServiceError):
    """Raised when a caller has view access but lacks a specific permission."""

    def __init__(
        self,
        permission: PermissionName,
        subject_type: SubjectType,
        subject_id: uuid.UUID,
    ) -> None:
        self.permission = permission
        self.subject_type = subject_type
        self.subject_id = subject_id
        super().__init__(
            f"Missing '{permission.value}' permission on "
            f"{subject_type.value} {subject_id}",
        )


class NodeVersionConflictError(NotesServiceError):
    """Raised when optimistic locking detects a version conflict."""

    def __init__(
        self,
        node_id: uuid.UUID,
        expected_version: int,
        actual_version: int,
    ) -> None:
        self.node_id = node_id
        self.expected_version = expected_version
        self.actual_version = actual_version
        super().__init__(
            f"Version conflict on node {node_id}: "
            f"expected {expected_version}, actual {actual_version}",
        )
