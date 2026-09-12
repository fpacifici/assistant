"""Alembic environment — resolves its connection via the app's own config."""

from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import create_engine, pool, text

from alembic import context
from assistant.models import schema as _schema  # noqa: F401  registers models on Base
from assistant.models.database import (
    Base,
    get_database_url,
    include_object_for_migrations,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
TARGET_SCHEMA = "assistant"


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection, emitting raw SQL."""
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        include_schemas=True,
        include_object=include_object_for_migrations,
        version_table_schema=TARGET_SCHEMA,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live DB connection."""
    # Postgres' default search_path is `"$user", public` — if the connecting
    # role happens to be named "assistant" (the default in
    # docker-compose.yml), `$user` makes the `assistant` schema *also* the
    # connection's implicit default schema. SQLAlchemy's dialect caches
    # "the default schema" from a query it runs itself immediately on
    # connect, before any of our own SQL gets a chance to run — so this must
    # be set via `connect_args`, not a `connection.execute()` after the
    # fact. Without it, Alembic normalizes "the default schema" to None
    # internally, and autogenerate sees the reflected side as schema=None
    # while the metadata side always says schema='assistant' explicitly — a
    # permanent, spurious mismatch that makes every table/constraint look
    # "added" on every run. Forcing search_path to `public` up front keeps
    # `assistant` unambiguously a named, non-default schema from Postgres'
    # point of view.
    connectable = create_engine(
        get_database_url(),
        poolclass=pool.NullPool,
        connect_args={"options": "-c search_path=public"},
    )

    with connectable.connect() as connection:
        # alembic_version lives in the `assistant` schema (version_table_schema
        # below), so that schema must exist before Alembic can even check/create
        # its own tracking table — before any migration (including the baseline,
        # which is the one that would otherwise create this schema) ever runs.
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS assistant"))
        connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            include_object=include_object_for_migrations,
            version_table_schema=TARGET_SCHEMA,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
