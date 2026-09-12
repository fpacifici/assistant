"""Database connection and session management."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

from langgraph.checkpoint.postgres import PostgresSaver
from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from alembic import command
from alembic.config import Config as AlembicConfig
from assistant.config import Config, DatabaseComponentsConfig

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine
    from sqlalchemy.orm.session import Session
    from sqlalchemy.sql.schema import SchemaItem

_REPO_ROOT = Path(__file__).resolve().parents[3]  # src/assistant/models/ -> repo root
_ALEMBIC_INI = _REPO_ROOT / "alembic.ini"

# Deterministic names for constraints that don't already have an explicit
# `name=` (most notably every plain `ForeignKey(...)` column shortcut in
# schema.py). Without this, Alembic's autogenerate can't reliably match
# unnamed constraints against what's already in the database and proposes
# dropping/recreating all of them on every single `revision --autogenerate`
# run, even with zero real schema changes. Explicitly-named constraints
# already in schema.py (e.g. `uq_notebook_name`) are unaffected — this only
# fills in names for ones that don't have one.
_NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base class for all database models."""

    metadata = MetaData(naming_convention=_NAMING_CONVENTION)


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


def upgrade_database(revision: str = "head") -> None:
    """Apply Alembic migrations up to `revision` (default: head)."""
    command.upgrade(AlembicConfig(str(_ALEMBIC_INI)), revision)


def downgrade_database(revision: str = "-1") -> None:
    """Revert Alembic migrations to `revision` (default: -1, one step back)."""
    command.downgrade(AlembicConfig(str(_ALEMBIC_INI)), revision)


def include_object_for_migrations(
    obj: SchemaItem,
    _name: str | None,
    type_: str,
    _reflected: bool,
    _compare_to: object | None,
) -> bool:
    """Alembic autogenerate filter: only ever consider the `assistant` schema.

    Without this, autogenerate (which needs `include_schemas=True` to see
    `assistant` at all) would also reflect `public` and could propose
    dropping tables this app doesn't own — e.g. langgraph's `PostgresSaver`
    checkpoint tables, which live outside `Base.metadata` entirely.

    Args mirror Alembic's `include_object` hook signature exactly (called
    positionally) — only `obj`/`type_` are actually used here.
    """
    if type_ == "table":
        return getattr(obj, "schema", None) == "assistant"
    table = getattr(obj, "table", None)
    return table is None or table.schema == "assistant"


def drop_database(engine: Engine | None = None) -> None:
    """Drop the assistant schema and all tables.

    For PostgreSQL, drops the 'assistant' schema (CASCADE). For SQLite,
    drops all tables in Base.metadata. Use before init_database to reset state.

    Args:
        engine: Optional SQLAlchemy engine. If not provided, a new one is created.

    Raises:
        Exception: If the drop operation fails.
    """
    if engine is None:
        engine = get_engine()

    dialect_name = engine.dialect.name
    if dialect_name == "postgresql":
        with engine.connect() as conn:
            conn.execute(text("DROP SCHEMA IF EXISTS assistant CASCADE"))
            conn.commit()
    else:
        # SQLite and others: drop tables via metadata
        from assistant.models import schema  # noqa: F401

        Base.metadata.drop_all(engine)


def init_database(engine: Engine | None = None) -> None:
    """Initialize database schema.

    PostgreSQL: applies all Alembic migrations (creates the `assistant`
    schema, the pgvector extension, and every table — see the baseline
    migration). SQLite (tests only): creates tables directly via
    `create_all`, since Alembic here targets a non-default Postgres schema
    SQLite can't represent.

    Args:
        engine: Optional SQLAlchemy engine. If not provided, a new one is created.
    """
    if engine is None:
        engine = get_engine()

    if engine.dialect.name == "postgresql":
        upgrade_database()
    else:
        # Import models to ensure they're registered with Base
        from assistant.models import schema  # noqa: F401

        Base.metadata.create_all(engine)

    with PostgresSaver.from_conn_string(get_database_url()) as checkpointer:
        checkpointer.setup()
