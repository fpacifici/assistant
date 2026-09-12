"""Tests for database connection and session management."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from assistant.models.database import (
    Base,
    downgrade_database,
    drop_database,
    get_database_url,
    get_engine,
    get_session_factory,
    include_object_for_migrations,
    init_database,
    upgrade_database,
)
from assistant.models.schema import (
    Document,
    DocumentFormat,
    ExternalSource,
)


def _strip_schemas_for_sqlite() -> dict[str, str | None]:
    """Strip schemas from all tables for SQLite compatibility.

    Returns a dict of original schemas keyed by table fullname.
    """
    original: dict[str, str | None] = {}
    for table in Base.metadata.sorted_tables:
        original[table.fullname] = table.schema
        table.schema = None

    for table in Base.metadata.sorted_tables:
        for col in table.columns:
            for fk in col.foreign_keys:
                fk._table_key = None  # type: ignore[attr-defined]
                ref_table_name = fk.column.table.name
                ref_col_name = fk.column.name
                ref_table = Base.metadata.tables.get(ref_table_name)
                if ref_table is not None:
                    fk.column = ref_table.columns[ref_col_name]  # type: ignore[assignment]

    return original


def _restore_schemas(original: dict[str, str | None]) -> None:
    """Restore original schemas on all tables."""
    for table in Base.metadata.sorted_tables:
        table.schema = original[table.fullname]


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


def test_init_database_with_in_memory_db() -> None:
    """Test initializing database with in-memory SQLite database."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    original = _strip_schemas_for_sqlite()

    try:
        with patch("assistant.models.database.PostgresSaver"):
            init_database(engine)

            inspector = inspect(engine)
            assert inspector.has_table("documents")
            assert inspector.has_table("external_sources")
            assert inspector.has_table("document_metadata")
            assert inspector.has_table("users")
            assert inspector.has_table("notebooks")
            assert inspector.has_table("notes")
            assert inspector.has_table("nodes")
    finally:
        _restore_schemas(original)


def test_init_database_postgresql_dialect_calls_upgrade_database() -> None:
    """Test that init_database runs Alembic migrations for PostgreSQL, not create_all."""
    mock_engine = MagicMock()
    mock_engine.dialect.name = "postgresql"

    with (
        patch("assistant.models.database.upgrade_database") as mock_upgrade,
        patch("assistant.models.database.Base") as mock_base,
        patch("assistant.models.database.PostgresSaver"),
    ):
        init_database(mock_engine)

        mock_upgrade.assert_called_once_with()
        mock_base.metadata.create_all.assert_not_called()


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
    original = _strip_schemas_for_sqlite()

    try:
        with patch("assistant.models.database.PostgresSaver"):
            init_database(engine)
        assert inspect(engine).has_table("documents")
        assert inspect(engine).has_table("external_sources")
        assert inspect(engine).has_table("nodes")

        drop_database(engine)

        assert not inspect(engine).has_table("documents")
        assert not inspect(engine).has_table("external_sources")
        assert not inspect(engine).has_table("nodes")
    finally:
        _restore_schemas(original)


def test_base_declarative_base() -> None:
    """Test that Base is a proper declarative base."""
    assert Base is not None
    assert hasattr(Base, "metadata")
    assert hasattr(Base, "registry")


def test_upgrade_database_default_revision() -> None:
    """Test that upgrade_database defaults to 'head' and uses the repo's alembic.ini."""
    with patch("assistant.models.database.command") as mock_command:
        upgrade_database()

        args, _ = mock_command.upgrade.call_args
        config, revision = args
        assert revision == "head"
        assert config.config_file_name.endswith("alembic.ini")


def test_upgrade_database_explicit_revision() -> None:
    """Test that upgrade_database passes through an explicit revision."""
    with patch("assistant.models.database.command") as mock_command:
        upgrade_database("abc123")

        args, _ = mock_command.upgrade.call_args
        _, revision = args
        assert revision == "abc123"


def test_downgrade_database_default_revision() -> None:
    """Test that downgrade_database defaults to '-1' (one step back)."""
    with patch("assistant.models.database.command") as mock_command:
        downgrade_database()

        args, _ = mock_command.downgrade.call_args
        config, revision = args
        assert revision == "-1"
        assert config.config_file_name.endswith("alembic.ini")


def test_downgrade_database_explicit_revision() -> None:
    """Test that downgrade_database passes through an explicit revision."""
    with patch("assistant.models.database.command") as mock_command:
        downgrade_database("base")

        args, _ = mock_command.downgrade.call_args
        _, revision = args
        assert revision == "base"


def test_include_object_for_migrations_table_in_assistant_schema() -> None:
    """Test that tables in the `assistant` schema are included."""
    table = MagicMock(schema="assistant")
    assert include_object_for_migrations(table, "t", "table", False, None) is True


def test_include_object_for_migrations_table_in_other_schema() -> None:
    """Test that tables outside the `assistant` schema are excluded."""
    table = MagicMock(schema="public")
    assert include_object_for_migrations(table, "t", "table", False, None) is False

    unscoped_table = MagicMock(schema=None)
    assert (
        include_object_for_migrations(unscoped_table, "t", "table", False, None) is False
    )


def test_include_object_for_migrations_non_table_follows_parent_table_schema() -> None:
    """Test that columns/indexes/constraints follow their parent table's schema."""
    column = MagicMock()
    column.table.schema = "assistant"
    assert include_object_for_migrations(column, "c", "column", False, None) is True

    other_column = MagicMock()
    other_column.table.schema = "public"
    assert (
        include_object_for_migrations(other_column, "c", "column", False, None) is False
    )


def test_include_object_for_migrations_object_without_table_is_included() -> None:
    """Test that an object with no `.table` attribute isn't excluded by mistake."""
    obj = object()
    assert include_object_for_migrations(obj, "x", "column", False, None) is True
