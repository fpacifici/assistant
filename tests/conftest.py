"""Shared pytest fixtures and configuration."""

from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import Table, create_engine
from sqlalchemy.orm import Session, sessionmaker

from assistant.config import Config
from assistant.models.database import Base
from assistant.models.schema import Document, DocumentMetadata, ExternalSource


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Provide a temporary directory for tests.

    Args:
        tmp_path: pytest's temporary path fixture.

    Returns:
        Path to temporary directory.
    """
    return tmp_path


@pytest.fixture
def sample_file(temp_dir: Path) -> Path:
    """Create a sample file for testing.

    Args:
        temp_dir: Temporary directory fixture.

    Returns:
        Path to sample file.
    """
    file_path = temp_dir / "sample.txt"
    file_path.write_text("sample content\n")
    return file_path
    # Cleanup handled by tmp_path


@pytest.fixture
def test_config(tmp_path: Path) -> Config:
    """Provide a test configuration.

    Args:
        tmp_path: Temporary directory fixture.

    Returns:
        Config instance with test settings.
    """
    # Create a temporary config file
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(
        "database:\n"
        "  host: localhost\n"
        "  port: 5432\n"
        "  user: test\n"
        "  password: test\n"
        "  name: test\n"
        "document_storage_path: " + str(tmp_path / "documents") + "\n"
        "external_sources:\n"
        "  fake:\n"
        "    enabled: true\n",
    )

    return Config(config_path=config_file)


@pytest.fixture
def document_storage_dir(tmp_path: Path) -> Path:
    """Provide a temporary directory for document storage.

    Args:
        tmp_path: Temporary directory fixture.

    Returns:
        Path to document storage directory.
    """
    storage_dir = tmp_path / "documents"
    storage_dir.mkdir(parents=True, exist_ok=True)
    return storage_dir


@pytest.fixture
def mock_database_url(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> str:
    """Provide a mock database URL for testing.

    Args:
        monkeypatch: pytest monkeypatch fixture.
        tmp_path: Temporary directory fixture.

    Returns:
        Database URL string.
    """
    # Use SQLite for testing
    db_path = tmp_path / "test.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    return db_url


@pytest.fixture
def db_session(tmp_path: Path) -> Iterator[Session]:  # noqa: ARG001
    """Provide a database session for testing.

    Uses in-memory SQLite database. SQLite doesn't support schemas,
    so we create table definitions without schemas for testing.

    Args:
        tmp_path: Temporary directory fixture.

    Yields:
        Database session.
    """
    # Use in-memory SQLite for testing
    database_url = "sqlite:///:memory:"
    engine = create_engine(database_url, echo=False)

    # SQLite doesn't support schemas, so we temporarily modify Base.metadata
    # to remove schemas from table definitions
    # Get the original table objects
    doc_table = cast(Table, Document.__table__)
    source_table = cast(Table, ExternalSource.__table__)
    metadata_table = cast(Table, DocumentMetadata.__table__)

    # Save original schemas
    doc_schema = doc_table.schema
    source_schema = source_table.schema
    metadata_schema = metadata_table.schema

    # Remove schemas temporarily - this must be done before any table operations
    doc_table.schema = None
    source_table.schema = None
    metadata_table.schema = None

    # SQLAlchemy looks up tables in metadata using a key that includes schema.
    # When we set schema = None, the table key changes, but the foreign key
    # constraint might still reference the old key. We need to ensure the FK
    # can find the referenced table in the no-schema namespace.
    #
    # The foreign key uses a string reference "external_sources.id", which should
    # work, but SQLAlchemy resolves it by looking up the table in metadata.
    # We need to ensure both tables are in the same metadata namespace.

    # Force SQLAlchemy to re-resolve the foreign keys by updating the constraints
    # Get the source_id column and its foreign key
    source_id_col = doc_table.columns["source_id"]
    for fk in list(source_id_col.foreign_keys):
        # Update the foreign key to explicitly reference source_table
        # This ensures it points to the table in the no-schema namespace
        fk._table_key = None  # type: ignore[attr-defined]  # Clear cached table key
        fk.column = source_table.columns["id"]  # type: ignore[assignment]

    # Ensure the foreign key from document_metadata to documents also points to the
    # no-schema documents table in this in-memory SQLite database.
    document_uuid_col = metadata_table.columns["document_uuid"]
    for fk in list(document_uuid_col.foreign_keys):
        fk._table_key = None  # type: ignore[attr-defined]
        fk.column = doc_table.columns["uuid"]  # type: ignore[assignment]

    try:
        # Create tables - SQLAlchemy should now resolve the foreign keys correctly
        # Create external_sources first
        source_table.create(engine, checkfirst=True)
        # Then create documents - the FK should now find external_sources
        doc_table.create(engine, checkfirst=True)
        # Finally create document_metadata - the FK should now find documents
        metadata_table.create(engine, checkfirst=True)

        # Create session - the ORM models will work
        session_factory = sessionmaker(bind=engine)
        session = session_factory()

        try:
            yield session
        finally:
            session.close()
            # Drop tables in reverse order
            Base.metadata.drop_all(
                engine,
                tables=[metadata_table, doc_table, source_table],
            )
    finally:
        # Restore original schemas
        doc_table.schema = doc_schema
        source_table.schema = source_schema
        metadata_table.schema = metadata_schema
