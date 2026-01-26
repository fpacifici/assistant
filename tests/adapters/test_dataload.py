"""Tests for DataLoad job."""

from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from assistant.adapters.dataload import load_data
from assistant.adapters.plugins.fake import FakeExternalSource
from assistant.adapters.registry import get_registry
from assistant.config import Config
from assistant.models.schema import Document, ExternalSource


def test_load_data_with_no_sources(test_config: Config, db_session: Session) -> None:
    """Test load_data with no external sources."""
    registry = get_registry()
    registry.register("fake", FakeExternalSource)

    # Mock the session factory to use our test session
    class SessionContext:
        def __enter__(self) -> Session:
            return db_session

        def __exit__(self, *args) -> None:
            pass

    def session_factory() -> SessionContext:
        return SessionContext()

    with patch(
        "assistant.adapters.dataload.get_session_factory",
    ) as mock_factory:
        mock_factory.return_value = session_factory
        # Should not raise an error, just log a warning
        load_data(config=test_config)


@pytest.mark.usefixtures("document_storage_dir")
def test_load_data_creates_documents(test_config: Config, db_session: Session) -> None:
    """Test that load_data creates documents in the database."""
    from assistant.adapters.registry import get_registry

    registry = get_registry()
    registry.register("fake", FakeExternalSource)

    # Create an external source in the database
    source = ExternalSource(provider="fake", provider_query="{}")
    db_session.add(source)
    db_session.commit()

    # Mock the session factory to use our test session
    class SessionContext:
        def __enter__(self) -> Session:
            return db_session

        def __exit__(self, *args):
            pass

    def session_factory() -> SessionContext:
        return SessionContext()

    with patch(
        "assistant.adapters.dataload.get_session_factory",
    ) as mock_factory:
        mock_factory.return_value = session_factory
        # Run load_data
        load_data(config=test_config)

    # Check that documents were created
    documents = db_session.query(Document).filter(Document.source_id == source.id).all()
    assert len(documents) >= 2  # Should have at least doc1 and doc2

    # Check document properties
    for doc in documents:
        assert doc.external_id in ["doc1", "doc2"]
        assert doc.title is not None
        assert doc.format is not None
        assert doc.source_id == source.id


def test_load_data_stores_content(
    test_config: Config,
    db_session: Session,
    document_storage_dir: Path,
) -> None:
    """Test that load_data stores document content in filesystem."""
    from assistant.adapters.content import read_content
    from assistant.adapters.registry import get_registry

    registry = get_registry()
    registry.register("fake", FakeExternalSource)

    # Create an external source
    source = ExternalSource(provider="fake", provider_query="{}")
    db_session.add(source)
    db_session.commit()

    # Mock the session factory to use our test session
    class SessionContext:
        def __enter__(self):
            return db_session

        def __exit__(self, *args):
            pass

    def session_factory():
        return SessionContext()

    with patch(
        "assistant.adapters.dataload.get_session_factory",
    ) as mock_factory:
        mock_factory.return_value = session_factory
        # Run load_data
        load_data(config=test_config)

    # Check that content files were created
    documents = db_session.query(Document).filter(Document.source_id == source.id).all()
    assert len(documents) > 0

    for doc in documents:
        content = read_content(document_storage_dir, doc.uuid)
        assert content is not None
        assert len(content.bytes) > 0
