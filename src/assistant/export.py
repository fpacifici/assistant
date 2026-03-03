from __future__ import annotations

"""Database and content export utilities.

This module implements the core logic to create a backup archive that contains:

* A `pg_dump` of the database (for manual recovery or inspection).
* A logical dump of application data (documents, external sources, and, when
  running on PostgreSQL, pgvector-backed embedding collections).
* A copy of the document storage directory.

The main entry point is :func:`run_export`, which is intended to be invoked by
CLI scripts and other orchestration layers.
"""

import json
import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, TypedDict, cast

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from assistant.config import Config, DatabaseComponentsConfig, DatabaseConfig
from assistant.models.database import get_engine
from assistant.models.schema import Document, ExternalSource

DB_DUMP_FILENAME = "db.dump"
LOGICAL_DATA_FILENAME = "data.json"
DOCUMENTS_DIRNAME = "documents"


class ExportedExternalSource(TypedDict):
    """Serialized representation of an external source."""

    id: str
    provider: str
    provider_query: str | None


class ExportedDocument(TypedDict):
    """Serialized representation of a document."""

    uuid: str
    external_id: str
    creation_datetime: str
    last_update_datetime: str
    title: str
    format: str
    source_id: str


class ExportedCollection(TypedDict, total=False):
    """Serialized representation of a vector collection."""

    uuid: str
    name: str
    cmetadata: dict[str, object] | None


class ExportedEmbedding(TypedDict, total=False):
    """Serialized representation of an embedding row."""

    id: str
    collection_id: str
    embedding: list[float]
    document: str | None
    cmetadata: dict[str, object] | None


class ExportedData(TypedDict):
    """Top-level structure for logical export data."""

    external_sources: list[ExportedExternalSource]
    documents: list[ExportedDocument]
    collections: list[ExportedCollection]
    embeddings: list[ExportedEmbedding]


PgDumpRunner = Callable[[Path], None]


@dataclass(frozen=True)
class _PgDumpConfig:
    """Internal configuration required to run pg_dump inside Docker."""

    user: str
    password: str | None
    database: str
    container_name: str


def _build_pg_dump_config(config: Config, *, container_name: str = "assistant-postgres") -> _PgDumpConfig:
    """Create pg_dump configuration from the application Config.

    Args:
        config: Application configuration instance.
        container_name: Name of the PostgreSQL container used for docker exec.

    Returns:
        Parsed configuration for invoking pg_dump.

    Raises:
        ValueError: If the database configuration does not provide the required
            fields to construct pg_dump arguments.
    """

    db_config: DatabaseConfig = config.get_database_config()
    url = db_config.get("url")
    if isinstance(url, str) and url:
        msg = (
            "Database configuration must use component fields (host/port/user/password/name) "
            "to support container-based pg_dump. A URL-only configuration cannot be used "
            "for automated pg_dump invocation."
        )
        raise ValueError(msg)

    components = cast("DatabaseComponentsConfig", db_config)
    return _PgDumpConfig(
        user=components["user"],
        password=components.get("password"),
        database=components["name"],
        container_name=container_name,
    )


def _default_pg_dump_runner(dump_path: Path, *, config: Config) -> None:
    """Run pg_dump inside the default Docker container.

    This uses ``docker exec`` to invoke pg_dump in the container named
    ``assistant-postgres`` (or the container name configured in Docker
    Compose). The dump is written to ``dump_path`` in custom format.

    Args:
        dump_path: Target path for the pg_dump output.
        config: Application configuration instance used to discover database
            credentials.

    Raises:
        subprocess.CalledProcessError: If the pg_dump command fails.
        ValueError: If the database configuration is incompatible with this
            runner.
    """

    dump_cfg = _build_pg_dump_config(config)
    env_args: list[str] = []
    if dump_cfg.password:
        env_args = ["-e", f"PGPASSWORD={dump_cfg.password}"]

    cmd: list[str] = [
        "docker",
        "exec",
        *env_args,
        dump_cfg.container_name,
        "pg_dump",
        "-U",
        dump_cfg.user,
        "-d",
        dump_cfg.database,
        "-Fc",
    ]

    dump_path.parent.mkdir(parents=True, exist_ok=True)
    with dump_path.open("wb") as dump_file:
        subprocess.run(cmd, check=True, stdout=dump_file)


def _serialize_datetime(value: datetime) -> str:
    """Serialize a datetime to an ISO 8601 string."""

    return value.isoformat()


def _export_application_data(session: Session) -> tuple[list[ExportedExternalSource], list[ExportedDocument]]:
    """Export application-level ORM entities using the given session.

    Args:
        session: SQLAlchemy session bound to the target database.

    Returns:
        A tuple containing the exported external sources and documents.
    """

    external_sources: list[ExportedExternalSource] = []
    for source in session.scalars(select(ExternalSource)):
        external_sources.append(
            {
                "id": str(source.id),
                "provider": source.provider,
                "provider_query": source.provider_query,
            },
        )

    documents: list[ExportedDocument] = []
    for document in session.scalars(select(Document)):
        documents.append(
            {
                "uuid": str(document.uuid),
                "external_id": document.external_id,
                "creation_datetime": _serialize_datetime(document.creation_datetime),
                "last_update_datetime": _serialize_datetime(document.last_update_datetime),
                "title": document.title,
                "format": document.format.value,
                "source_id": str(document.source_id),
            },
        )

    return external_sources, documents


def _export_vector_data(engine: Engine) -> tuple[list[ExportedCollection], list[ExportedEmbedding]]:
    """Export vector collection and embedding data when using PostgreSQL.

    This function inspects the langchain-postgres vector store tables
    (``langchain_pg_collection`` and ``langchain_pg_embedding``) if they are
    available. When running against a non-PostgreSQL backend (for example
    SQLite in tests), this function returns empty lists.

    Args:
        engine: SQLAlchemy engine connected to the target database.

    Returns:
        A tuple containing collections and embeddings data.
    """

    if engine.dialect.name != "postgresql":
        return [], []

    # Import lazily to avoid adding langchain_postgres as an unconditional import
    # requirement for consumers that never use export functionality.
    from langchain_postgres.vectorstores import (  # type: ignore[import-untyped]
        Base as LCBase,
        _get_embedding_collection_store,
    )

    # Ensure the ORM classes for the vector tables are defined and bound to the
    # langchain-postgres declarative base.
    embedding_store_cls, collection_store_cls = _get_embedding_collection_store()

    # Reflect existing tables if they already exist; otherwise, there is nothing
    # to export.
    LCBase.metadata.bind = engine
    existing_tables = engine.dialect.get_table_names(engine.connect())
    if (
        "langchain_pg_collection" not in existing_tables
        or "langchain_pg_embedding" not in existing_tables
    ):
        return [], []

    session_factory = sessionmaker(bind=engine)
    collections: list[ExportedCollection] = []
    embeddings: list[ExportedEmbedding] = []

    with session_factory() as session:
        for collection in session.scalars(select(collection_store_cls)):
            collections.append(
                {
                    "uuid": str(collection.uuid),
                    "name": collection.name,
                    "cmetadata": cast("dict[str, object] | None", collection.cmetadata),
                },
            )

        for embedding in session.scalars(select(embedding_store_cls)):
            vector: Iterable[float] | None
            if embedding.embedding is None:
                vector = None
            else:
                # The pgvector type exposes a vector-like Python value; converting
                # to list[float] makes the value JSON-serializable.
                vector = [float(component) for component in embedding.embedding]

            embeddings.append(
                {
                    "id": str(embedding.id),
                    "collection_id": str(embedding.collection_id),
                    "embedding": list(vector) if vector is not None else [],
                    "document": embedding.document,
                    "cmetadata": cast("dict[str, object] | None", embedding.cmetadata),
                },
            )

    return collections, embeddings


def _write_logical_dump(engine: Engine, output_path: Path) -> None:
    """Write a logical dump of application and vector data to a JSON file.

    Args:
        engine: SQLAlchemy engine connected to the target database.
        output_path: File where the JSON data will be written.
    """

    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        external_sources, documents = _export_application_data(session)

    collections, embeddings = _export_vector_data(engine)

    data: ExportedData = {
        "external_sources": external_sources,
        "documents": documents,
        "collections": collections,
        "embeddings": embeddings,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def run_export(config: Config, output_path: Path, *, pg_dump_runner: PgDumpRunner | None = None) -> None:
    """Create a backup archive containing database and document contents.

    The produced ``tar.gz`` archive has the following layout:

    - ``db.dump``: Raw output from ``pg_dump`` (custom format).
    - ``data.json``: Logical export of application and (when available) vector
      data.
    - ``documents/``: Copy of the configured document storage directory.

    Args:
        config: Application configuration instance.
        output_path: Target path for the resulting ``.tar.gz`` archive.
        pg_dump_runner: Optional custom function used to create the pg_dump
            file. When ``None``, a default Docker-based runner is used that
            executes pg_dump inside the ``assistant-postgres`` container.

    Raises:
        subprocess.CalledProcessError: If the default pg_dump command fails.
        ValueError: If the database configuration is incompatible with the
            default pg_dump runner.
    """

    engine = get_engine()
    output_path = output_path.resolve()

    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)

        db_dump_path = tmp_dir / DB_DUMP_FILENAME
        logical_dump_path = tmp_dir / LOGICAL_DATA_FILENAME
        documents_tmp_dir = tmp_dir / DOCUMENTS_DIRNAME

        # 1. Run pg_dump (or the caller-provided equivalent).
        if pg_dump_runner is not None:
            pg_dump_runner(db_dump_path)
        else:
            _default_pg_dump_runner(db_dump_path, config=config)

        # 2. Write logical export of application and vector data.
        _write_logical_dump(engine, logical_dump_path)

        # 3. Copy document storage directory.
        storage_path = config.get_document_storage_path()
        if storage_path.exists():
            shutil.copytree(storage_path, documents_tmp_dir, dirs_exist_ok=True)
        else:
            documents_tmp_dir.mkdir(parents=True, exist_ok=True)

        # 4. Create the final tar.gz archive with stable, predictable names.
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(output_path, "w:gz") as tar:
            tar.add(db_dump_path, arcname=DB_DUMP_FILENAME)
            tar.add(logical_dump_path, arcname=LOGICAL_DATA_FILENAME)
            tar.add(documents_tmp_dir, arcname=DOCUMENTS_DIRNAME)

