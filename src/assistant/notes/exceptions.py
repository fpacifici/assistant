"""Notes service exceptions."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid


class NotesServiceError(Exception):
    """Base exception for the notes service."""


class UserNotFoundError(NotesServiceError):
    """Raised when a user is not found."""


class NotebookNotFoundError(NotesServiceError):
    """Raised when a notebook is not found."""


class NoteNotFoundError(NotesServiceError):
    """Raised when a note is not found."""


class NodeNotFoundError(NotesServiceError):
    """Raised when a node is not found."""


class InvalidNodeTypeError(NotesServiceError):
    """Raised when an operation is applied to the wrong node type."""


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
