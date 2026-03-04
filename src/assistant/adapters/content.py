"""Document content handling for filesystem storage."""

import uuid
from pathlib import Path

from assistant.models.content import DocumentContent


def get_content_path(base_dir: Path, document_uuid: uuid.UUID) -> Path:
    """Get the filesystem path for a document's content.

    Args:
        base_dir: Base directory for document storage.
        document_uuid: UUID of the document.

    Returns:
        Path to the document content file.
    """
    return base_dir / str(document_uuid)


def read_content(
    base_dir: Path,
    document_uuid: uuid.UUID,
) -> DocumentContent | None:
    """Read document content from the filesystem.

    Args:
        base_dir: Base directory for document storage.
        document_uuid: UUID of the document.

    Returns:
        DocumentContent if file exists, None otherwise.
    """
    content_path = get_content_path(base_dir, document_uuid)
    if not content_path.exists():
        return None

    return DocumentContent(
        uuid=document_uuid,
        bytes=content_path.read_bytes(),
    )


def write_content(
    base_dir: Path,
    content: DocumentContent,
) -> None:
    """Write document content to the filesystem.

    Args:
        base_dir: Base directory for document storage.
        content: DocumentContent to write.

    Raises:
        OSError: If the file cannot be written.
    """
    base_dir.mkdir(parents=True, exist_ok=True)
    content_path = get_content_path(base_dir, content.uuid)
    content_path.write_bytes(content.bytes)


def delete_content(base_dir: Path, document_uuid: uuid.UUID) -> None:
    """Delete document content from the filesystem.

    Args:
        base_dir: Base directory for document storage.
        document_uuid: UUID of the document to delete.

    Raises:
        OSError: If the file cannot be deleted.
    """
    content_path = get_content_path(base_dir, document_uuid)
    if content_path.exists():
        content_path.unlink()
