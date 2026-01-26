"""Database connection and session management."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from assistant.config import Config, DatabaseComponentsConfig

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine
    from sqlalchemy.orm.session import Session


class Base(DeclarativeBase):
    """Base class for all database models."""


def get_database_url() -> str:
    """Get database connection URL from configuration.

    Uses the Config class to read database connection parameters from
    config.yaml file, with support for environment-variable overrides.

    Returns:
        Database connection URL string.

    Raises:
        ValueError: If required configuration is missing.
    """
    config = Config()
    db_config = config.get_database_config()
    url = db_config.get("url")
    if isinstance(url, str) and url:
        return url

    components = cast("DatabaseComponentsConfig", db_config)
    return (
        f"postgresql://{components['user']}:{components['password']}@"
        f"{components['host']}:{components['port']}/{components['name']}"
    )


def get_engine() -> Engine:
    """Create and return SQLAlchemy engine.

    Returns:
        SQLAlchemy engine instance.
    """
    database_url = get_database_url()
    return create_engine(database_url, echo=False)


def get_session_factory() -> sessionmaker[Session]:
    """Create and return session factory.

    Returns:
        Session factory instance.
    """
    engine = get_engine()
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def create_schema(engine: Engine | None = None) -> None:
    """Create the assistant schema in the database.

    Args:
        engine: Optional SQLAlchemy engine. If not provided, a new one is created.
    """
    if engine is None:
        engine = get_engine()

    with engine.connect() as conn:
        # Create schema if it doesn't exist
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS assistant"))
        conn.commit()


def init_database(engine: Engine | None = None) -> None:
    """Initialize database schema and create all tables.

    Args:
        engine: Optional SQLAlchemy engine. If not provided, a new one is created.
    """
    if engine is None:
        engine = get_engine()

    # Create schema first
    create_schema(engine)

    # Import models to ensure they're registered with Base
    from assistant.models import schema  # noqa: F401

    # Create all tables
    # The schema is specified in the table definitions (__table_args__)
    # SQLAlchemy 2.0 doesn't accept schema parameter in create_all
    Base.metadata.create_all(engine)
