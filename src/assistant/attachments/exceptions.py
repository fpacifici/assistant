"""Attachment-specific exceptions."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid


class AttachmentNotFoundError(Exception):
    """Raised when a File record does not exist."""

    def __init__(self, file_id: uuid.UUID | str) -> None:
        super().__init__(f"File not found: {file_id}")
        self.file_id = file_id


class FileStateError(Exception):
    """Raised when a file operation is invalid for the current state."""

    def __init__(self, file_id: uuid.UUID | str, current: str, expected: str) -> None:
        super().__init__(f"File {file_id} is in state '{current}', expected '{expected}'")
        self.file_id = file_id
        self.current = current
        self.expected = expected


class FileExpiredError(Exception):
    """Raised when a file upload TTL has elapsed before completion."""

    def __init__(self, file_id: uuid.UUID | str) -> None:
        super().__init__(f"File upload expired: {file_id}")
        self.file_id = file_id


class FileAccessDeniedError(Exception):
    """Raised when the acting user does not own the note the file belongs to."""

    def __init__(self, file_id: uuid.UUID | str) -> None:
        super().__init__(f"Access denied for file: {file_id}")
        self.file_id = file_id
