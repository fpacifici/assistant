"""Tests for database connection and session management."""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from assistant.models.database import (
    Base,
    create_schema,
    drop_database,
    get_database_url,
    get_engine,
    get_session_factory,
    init_database,
)
from assistant.models.schema import Document, DocumentFormat, ExternalSource


def test_get_database_url_from_config() -> None:
    """Test getting database URL from config file."""
    # Mock the Config class import inside get_database_url
    with patch("assistant.models.database.Config") as mock_config_class:
        mock_config_instance = mock_config_class.return_value
        mock_config_instance.get_database_config.return_value = {
            "host": "testhost",
            "port": 5433,
            "user": "testuser",
            "password": "testpass",
            "name": "testdb",
        }

        url = get_database_url()
        assert "testuser" in url
        assert "testhost" in url
        assert "5433" in url
        assert "testdb" in url


def test_get_database_url_from_env() -> None:
    """Test getting database URL from environment variable."""
    test_url = "postgresql://envuser:envpass@envhost:5434/envdb"

    # Mock the Config class import inside get_database_url
    with patch("assistant.models.database.Config") as mock_config_class:
        mock_config_instance = mock_config_class.return_value
        mock_config_instance.get_database_config.return_value = {
            "url": test_url,
        }

        url = get_database_url()
        assert url == test_url


def test_get_engine_with_in_memory_db() -> None:
    """Test creating engine with in-memory SQLite database."""
    with patch("assistant.models.database.get_database_url") as mock_url:
        mock_url.return_value = "sqlite:///:memory:"
        engine = get_engine()

        assert engine is not None
        # Test that we can connect
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            assert result.scalar() == 1


def test_get_session_factory() -> None:
    """Test creating session factory."""
    with patch("assistant.models.database.get_database_url") as mock_url:
        mock_url.return_value = "sqlite:///:memory:"
        session_factory = get_session_factory()

        assert session_factory is not None

        # Test that we can create a session
        with session_factory() as session:
            assert isinstance(session, Session)


def test_create_schema_with_in_memory_db() -> None:
    """Test creating schema with in-memory SQLite database."""
    # SQLite doesn't support schemas, so CREATE SCHEMA will fail
    # This test verifies the function attempts to create the schema
    engine = create_engine("sqlite:///:memory:", echo=False)

    # SQLite will raise OperationalError for CREATE SCHEMA
    # This is expected behavior - the function is designed for PostgreSQL
    with pytest.raises(OperationalError, match='near "SCHEMA"'):
        create_schema(engine)


def test_init_database_with_in_memory_db() -> None:
    """Test initializing database with in-memory SQLite database."""
    engine = create_engine("sqlite:///:memory:", echo=False)

    # For SQLite, we need to handle schemas differently
    # Temporarily remove schemas from table definitions

    doc_table = Document.__table__
    source_table = ExternalSource.__table__

    # Save and remove schemas
    doc_schema = doc_table.schema
    source_schema = source_table.schema
    doc_table.schema = None
    source_table.schema = None

    # Update foreign key
    source_id_col = doc_table.columns["source_id"]
    for fk in list(source_id_col.foreign_keys):
        fk._table_key = None
        fk.column = source_table.columns["id"]

    try:
        # Mock create_schema to skip it (SQLite doesn't support schemas)
        with patch("assistant.models.database.create_schema"):
            # Initialize database
            init_database(engine)

            # Verify tables were created
            inspector = inspect(engine)
            assert inspector.has_table("documents")
            assert inspector.has_table("external_sources")
    finally:
        # Restore schemas
        doc_table.schema = doc_schema
        source_table.schema = source_schema


def test_init_database_creates_tables(db_session: Session) -> None:
    """Test that init_database creates all required tables."""

    # Verify we can create and query models
    source = ExternalSource(provider="test", provider_query="{}")
    db_session.add(source)
    db_session.flush()

    doc = Document(
        external_id="test1",
        creation_datetime=datetime.now(UTC),
        last_update_datetime=datetime.now(UTC),
        title="Test",
        format=DocumentFormat.TEXT,
        source_id=source.id,
    )
    db_session.add(doc)
    db_session.commit()

    # Verify we can query
    sources = db_session.query(ExternalSource).all()
    assert len(sources) == 1

    documents = db_session.query(Document).all()
    assert len(documents) == 1
    assert documents[0].external_id == "test1"


def test_drop_database_with_sqlite() -> None:
    """Test drop_database with SQLite drops tables."""
    engine = create_engine("sqlite:///:memory:", echo=False)

    # Set up tables (same schema-stripping as test_init_database_with_in_memory_db)
    doc_table = Document.__table__
    source_table = ExternalSource.__table__
    doc_schema = doc_table.schema
    source_schema = source_table.schema
    doc_table.schema = None
    source_table.schema = None
    source_id_col = doc_table.columns["source_id"]
    for fk in list(source_id_col.foreign_keys):
        fk._table_key = None
        fk.column = source_table.columns["id"]

    try:
        with patch("assistant.models.database.create_schema"):
            init_database(engine)
        assert inspect(engine).has_table("documents")
        assert inspect(engine).has_table("external_sources")

        drop_database(engine)

        assert not inspect(engine).has_table("documents")
        assert not inspect(engine).has_table("external_sources")
    finally:
        doc_table.schema = doc_schema
        source_table.schema = source_schema


def test_base_declarative_base() -> None:
    """Test that Base is a proper declarative base."""
    assert Base is not None
    assert hasattr(Base, "metadata")
    assert hasattr(Base, "registry")
