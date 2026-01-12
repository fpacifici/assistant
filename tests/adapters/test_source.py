"""Tests for adapters source interface."""

from datetime import UTC, datetime

import pytest

from assistant.adapters.content import DocumentContent
from assistant.adapters.source import ExternalSource


def test_external_source_is_abstract() -> None:
    """Test that ExternalSource cannot be instantiated directly."""
    with pytest.raises(TypeError):
        ExternalSource()  # type: ignore[abstract]


def test_external_source_interface_methods() -> None:
    """Test that ExternalSource defines required abstract methods."""
    # Check that the class has the required methods
    assert hasattr(ExternalSource, "get_document")
    assert hasattr(ExternalSource, "list_documents")

    # Check that they are abstract
    assert getattr(ExternalSource.get_document, "__isabstractmethod__", False)
    assert getattr(ExternalSource.list_documents, "__isabstractmethod__", False)


def test_fake_external_source_implements_interface() -> None:
    """Test that FakeExternalSource implements the interface."""
    from assistant.adapters.plugins.fake import FakeExternalSource

    fake = FakeExternalSource({})

    # Should be able to call the methods
    assert isinstance(fake, ExternalSource)
    assert hasattr(fake, "get_document")
    assert hasattr(fake, "list_documents")

    # Should be able to list documents
    since = datetime.min.replace(tzinfo=UTC)
    doc_ids = fake.list_documents(since, {})
    assert isinstance(doc_ids, list)
    assert len(doc_ids) > 0

    # Should be able to get a document
    if doc_ids:
        doc = fake.get_document(doc_ids[0])
        assert isinstance(doc, DocumentContent)
        assert doc.uuid is not None
        assert len(doc.bytes) > 0
