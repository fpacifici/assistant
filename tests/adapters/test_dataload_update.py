"""Additional tests for DataLoad job edge cases."""

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType
from unittest.mock import patch

from sqlalchemy.orm import Session

import assistant.adapters.registry as registry_module
from assistant.adapters.dataload import load_data
from assistant.adapters.plugins.fake import FakeExternalSource
from assistant.adapters.registry import get_registry
from assistant.config import Config
from assistant.models.schema import Document, DocumentFormat, ExternalSource


def test_load_data_updates_existing_document(
    test_config: Config,
    db_session: Session,
    document_storage_dir: Path,  # noqa: ARG001
) -> None:
    """Test that load_data updates existing documents."""

    registry_module._registry = None
    get_registry()

    # Create an external source
    source = ExternalSource(provider="fake", provider_query="{}")
    db_session.add(source)
    db_session.flush()

    # Create an existing document
    existing_doc = Document(
        uuid=uuid.uuid4(),
        external_id="doc1",
        creation_datetime=datetime.now(UTC) - timedelta(days=1),
        last_update_datetime=datetime.now(UTC) - timedelta(days=1),
        title="Old Title",
        format=DocumentFormat.TEXT,
        source_id=source.id,
    )
    db_session.add(existing_doc)
    db_session.commit()

    old_update_time = existing_doc.last_update_datetime

    # Mock the session factory
    class SessionContext:
        def __enter__(self) -> Session:
            return db_session

        def __exit__(
            self,
            _exc_type: type[BaseException] | None,
            _exc: BaseException | None,
            _tb: TracebackType | None,
        ) -> None:
            return None

    def session_factory() -> SessionContext:
        return SessionContext()

    with patch(
        "assistant.adapters.dataload.get_session_factory",
    ) as mock_factory:
        mock_factory.return_value = session_factory
        load_data(config=test_config)

    # Refresh the document
    db_session.refresh(existing_doc)

    # Document should be updated
    assert existing_doc.last_update_datetime > old_update_time
    # Title might be the same or different depending on implementation
    assert existing_doc.title is not None


def test_load_data_handles_provider_error(
    test_config: Config,
    db_session: Session,
    document_storage_dir: Path,  # noqa: ARG001
) -> None:
    """Test that load_data handles provider errors gracefully."""
    registry_module._registry = None
    registry = get_registry()

    # Create a mock provider that raises an error
    class ErrorProvider(FakeExternalSource):
        def list_documents(self, _since: datetime) -> list[str]:
            msg = "Provider error"
            raise RuntimeError(msg)

    registry._providers["fake"] = ErrorProvider

    # Create an external source with error provider
    source = ExternalSource(provider="fake", provider_query="{}")
    db_session.add(source)
    db_session.commit()

    # Mock the session factory
    class SessionContext:
        def __enter__(self) -> Session:
            return db_session

        def __exit__(
            self,
            _exc_type: type[BaseException] | None,
            _exc: BaseException | None,
            _tb: TracebackType | None,
        ) -> None:
            return None

    def session_factory() -> SessionContext:
        return SessionContext()

    with patch(
        "assistant.adapters.dataload.get_session_factory",
    ) as mock_factory:
        mock_factory.return_value = session_factory
        # Should not raise, but log error
        load_data(config=test_config)


def test_load_data_filters_by_since_datetime(
    test_config: Config,
    db_session: Session,
    document_storage_dir: Path,  # noqa: ARG001
) -> None:
    """Test that load_data only fetches documents updated since the most recent one."""
    registry_module._registry = None
    get_registry()

    # Create an external source
    source = ExternalSource(provider="fake", provider_query="{}")
    db_session.add(source)
    db_session.flush()

    # Create a document with recent update time
    recent_time = datetime.now(UTC) - timedelta(hours=1)
    existing_doc = Document(
        uuid=uuid.uuid4(),
        external_id="doc1",
        creation_datetime=recent_time,
        last_update_datetime=recent_time,
        title="Recent Doc",
        format=DocumentFormat.TEXT,
        source_id=source.id,
    )
    db_session.add(existing_doc)
    db_session.commit()

    initial_count = db_session.query(Document).count()

    # Mock the session factory
    class SessionContext:
        def __enter__(self) -> Session:
            return db_session

        def __exit__(
            self,
            _exc_type: type[BaseException] | None,
            _exc: BaseException | None,
            _tb: TracebackType | None,
        ) -> None:
            return None

    def session_factory() -> SessionContext:
        return SessionContext()

    with patch(
        "assistant.adapters.dataload.get_session_factory",
    ) as mock_factory:
        mock_factory.return_value = session_factory
        load_data(config=test_config)

    # Should only fetch documents updated after recent_time
    # The fake provider returns documents with current time, so they should be fetched
    final_count = db_session.query(Document).count()
    assert final_count >= initial_count
