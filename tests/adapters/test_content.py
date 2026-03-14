"""Tests for document content handling."""

import uuid
from pathlib import Path

from assistant.adapters.content import (
    DocumentContent,
    delete_content,
    get_content_path,
    read_content,
    write_content,
)


def test_get_content_path(document_storage_dir: Path) -> None:
    """Test getting content path for a document."""
    doc_uuid = uuid.uuid4()
    path = get_content_path(document_storage_dir, doc_uuid)

    assert path == document_storage_dir / str(doc_uuid)


def test_write_and_read_content(document_storage_dir: Path) -> None:
    """Test writing and reading document content."""
    doc_uuid = uuid.uuid4()
    content_bytes = b"Test document content"

    content = DocumentContent(uuid=doc_uuid, bytes=content_bytes)

    # Write content
    write_content(document_storage_dir, content)

    # Read content
    read = read_content(document_storage_dir, doc_uuid)

    assert read is not None
    assert read.uuid == doc_uuid
    assert read.bytes == content_bytes


def test_read_nonexistent_content(document_storage_dir: Path) -> None:
    """Test reading content that doesn't exist."""
    doc_uuid = uuid.uuid4()

    content = read_content(document_storage_dir, doc_uuid)

    assert content is None


def test_delete_content(document_storage_dir: Path) -> None:
    """Test deleting document content."""
    doc_uuid = uuid.uuid4()
    content = DocumentContent(uuid=doc_uuid, bytes=b"Test content")

    # Write content
    write_content(document_storage_dir, content)

    # Verify it exists
    assert read_content(document_storage_dir, doc_uuid) is not None

    # Delete content
    delete_content(document_storage_dir, doc_uuid)

    # Verify it's gone
    assert read_content(document_storage_dir, doc_uuid) is None
