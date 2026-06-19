"""Shared pytest fixtures and configuration."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from assistant.config import Config
from assistant.models import schema as _schema  # noqa: F401
from assistant.models.database import Base


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
    so we temporarily strip schemas from all tables and re-resolve
    foreign keys before creating them.

    Args:
        tmp_path: Temporary directory fixture.

    Yields:
        Database session.
    """
    database_url = "sqlite:///:memory:"
    engine = create_engine(database_url, echo=False)

    tables = Base.metadata.sorted_tables
    original_schemas: dict[str, str | None] = {}

    for table in tables:
        original_schemas[table.fullname] = table.schema
        table.schema = None

    for table in tables:
        for col in table.columns:
            for fk in col.foreign_keys:
                fk._table_key = None  # type: ignore[attr-defined]
                ref_table_name = fk.column.table.name
                ref_col_name = fk.column.name
                ref_table = Base.metadata.tables.get(ref_table_name)
                if ref_table is not None:
                    fk.column = ref_table.columns[ref_col_name]  # type: ignore[assignment]

    try:
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine)
        session = session_factory()

        try:
            yield session
        finally:
            session.close()
            Base.metadata.drop_all(engine)
    finally:
        for table in tables:
            table.schema = original_schemas[table.fullname]
