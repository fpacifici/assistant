"""Tests for fake plugin implementation."""

from datetime import UTC, datetime

import pytest

from assistant.adapters.content import DocumentContent
from assistant.adapters.plugins.fake import FakeExternalSource
from assistant.adapters.source import ExternalSourceInstanceConfig


def test_fake_external_source_creation() -> None:
    """Test creating a FakeExternalSource."""
    fake = FakeExternalSource(ExternalSourceInstanceConfig(provider_config={}, query_params={}))
    assert fake is not None


def test_fake_list_documents() -> None:
    """Test listing documents from fake source."""
    fake = FakeExternalSource(ExternalSourceInstanceConfig(provider_config={}, query_params={}))
    since = datetime.min.replace(tzinfo=UTC)

    doc_ids = fake.list_documents(since)
    assert isinstance(doc_ids, list)
    assert len(doc_ids) >= 2  # Should have at least doc1 and doc2


def test_fake_get_document() -> None:
    """Test getting a document from fake source."""
    fake = FakeExternalSource(ExternalSourceInstanceConfig(provider_config={}, query_params={}))

    doc = fake.get_document("doc1")
    assert isinstance(doc, DocumentContent)
    assert doc.uuid is not None
    assert len(doc.bytes) > 0
    assert b"Mock document 1" in doc.bytes


def test_fake_get_nonexistent_document() -> None:
    """Test getting a nonexistent document raises error."""
    fake = FakeExternalSource(ExternalSourceInstanceConfig(provider_config={}, query_params={}))

    with pytest.raises(ValueError, match="not found"):
        fake.get_document("nonexistent")


def test_fake_list_documents_with_since_filter() -> None:
    """Test that list_documents filters by since datetime."""
    fake = FakeExternalSource(ExternalSourceInstanceConfig(provider_config={}, query_params={}))

    # Get all documents
    all_docs = fake.list_documents(datetime.min.replace(tzinfo=UTC))

    # Get documents since a future date (should be empty)
    future = datetime.now(UTC).replace(year=2100)
    future_docs = fake.list_documents(future)

    assert len(all_docs) > len(future_docs)


def test_fake_document_uuid_deterministic() -> None:
    """Test that fake document UUIDs are deterministic."""
    fake1 = FakeExternalSource(ExternalSourceInstanceConfig(provider_config={}, query_params={}))
    fake2 = FakeExternalSource(ExternalSourceInstanceConfig(provider_config={}, query_params={}))

    doc1 = fake1.get_document("doc1")
    doc2 = fake2.get_document("doc1")

    assert doc1.uuid == doc2.uuid
