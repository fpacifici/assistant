from __future__ import annotations

"""Database and content restore utilities.

This module restores database contents and documents from an archive produced by
``assistant.export.run_export``. The implementation is intentionally logical:

* Recreates the application schema using :mod:`assistant.models.database`.
* Clears existing application data and, when applicable, langchain-postgres
  vector store tables.
* Re-inserts rows using SQLAlchemy so that compatible schema changes can be
  handled gracefully.
"""

import json
import shutil
import tarfile
import tempfile
import uuid as uuid_module
from datetime import datetime
from pathlib import Path
from typing import Iterable, TypedDict, cast

from sqlalchemy import delete, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from assistant.config import Config
from assistant.export import DOCUMENTS_DIRNAME, LOGICAL_DATA_FILENAME
from assistant.models.database import drop_database, get_engine, init_database
from assistant.models.schema import Document, DocumentFormat, DocumentMetadata, ExternalSource


class ImportedExternalSource(TypedDict):
    """Imported representation of an external source."""

    id: str
    provider: str
    provider_query: str | None


class ImportedDocument(TypedDict):
    """Imported representation of a document."""

    uuid: str
    external_id: str
    creation_datetime: str
    last_update_datetime: str
    title: str
    format: str
    source_id: str


class ImportedDocumentMetadata(TypedDict):
    """Imported representation of a document metadata entry."""

    document_uuid: str
    key: str
    value: str


class ImportedCollection(TypedDict, total=False):
    """Imported representation of a vector collection."""

    uuid: str
    name: str
    cmetadata: dict[str, object] | None


class ImportedEmbedding(TypedDict, total=False):
    """Imported representation of an embedding row."""

    id: str
    collection_id: str
    embedding: list[float]
    document: str | None
    cmetadata: dict[str, object] | None


class ImportedData(TypedDict):
    """Top-level structure for logical import data."""

    external_sources: list[ImportedExternalSource]
    documents: list[ImportedDocument]
    document_metadata: list[ImportedDocumentMetadata]
    collections: list[ImportedCollection]
    embeddings: list[ImportedEmbedding]


def _parse_datetime(value: str) -> datetime:
    """Parse an ISO 8601 datetime string."""

    return datetime.fromisoformat(value)


def _load_import_data(json_path: Path) -> ImportedData:
    """Load and validate logical import data from the given JSON file.

    Args:
        json_path: Path to the JSON file created by the export step.

    Returns:
        Parsed import data.
    """

    raw = json_path.read_text(encoding="utf-8")
    data = cast("ImportedData", json.loads(raw))
    data.setdefault("collections", [])
    data.setdefault("embeddings", [])
    data.setdefault("document_metadata", [])
    return data


def _reset_vector_tables(engine: Engine) -> None:
    """Drop and recreate langchain-postgres vector tables when on PostgreSQL.

    Args:
        engine: SQLAlchemy engine connected to the target database.
    """

    if engine.dialect.name != "postgresql":
        return

    from langchain_postgres.vectorstores import Base as LCBase, _get_embedding_collection_store

    # Ensure ORM classes for the vector tables are defined and bound, then drop
    # and recreate the tables.
    _get_embedding_collection_store()
    LCBase.metadata.bind = engine
    LCBase.metadata.drop_all(bind=engine)
    LCBase.metadata.create_all(bind=engine)


def _clear_application_data(session: Session) -> None:
    """Delete all application-level data from the current database.

    The order matters because of foreign key constraints: metadata depends on
    documents, and documents depend on external sources.
    """

    session.execute(delete(DocumentMetadata))
    session.execute(delete(Document))
    session.execute(delete(ExternalSource))


def _restore_application_data(session: Session, data: ImportedData) -> None:
    """Restore documents and external sources using ORM inserts.

    Args:
        session: SQLAlchemy session bound to the target database.
        data: Parsed import data.
    """

    for source_data in data["external_sources"]:
        source = ExternalSource(
            id=uuid_module.UUID(source_data["id"]),
            provider=source_data["provider"],
            provider_query=source_data["provider_query"],
        )
        session.add(source)

    for document_data in data["documents"]:
        document = Document(
            uuid=uuid_module.UUID(document_data["uuid"]),
            external_id=document_data["external_id"],
            creation_datetime=_parse_datetime(document_data["creation_datetime"]),
            last_update_datetime=_parse_datetime(document_data["last_update_datetime"]),
            title=document_data["title"],
            format=DocumentFormat(document_data["format"]),
            source_id=uuid_module.UUID(document_data["source_id"]),
        )
        session.add(document)

    for metadata_data in data.get("document_metadata", []):
        metadata = DocumentMetadata(
            document_uuid=uuid_module.UUID(metadata_data["document_uuid"]),
            key=metadata_data["key"],
            value=metadata_data["value"],
        )
        session.add(metadata)


def _restore_vector_data(engine: Engine, data: ImportedData) -> None:
    """Restore vector collections and embeddings when using PostgreSQL.

    Args:
        engine: SQLAlchemy engine connected to the target database.
        data: Parsed import data.
    """

    if engine.dialect.name != "postgresql":
        return

    from langchain_postgres.vectorstores import Base as LCBase, _get_embedding_collection_store

    embedding_store_cls, collection_store_cls = _get_embedding_collection_store()
    LCBase.metadata.bind = engine

    session_factory = sessionmaker(bind=engine)
    with session_factory() as session:
        # Clear existing vector data before inserting new rows.
        session.execute(text("DELETE FROM langchain_pg_embedding"))
        session.execute(text("DELETE FROM langchain_pg_collection"))

        for collection_data in data.get("collections", []):
            collection = collection_store_cls(
                uuid=uuid_module.UUID(collection_data["uuid"]),
                name=collection_data["name"],
                cmetadata=collection_data.get("cmetadata"),
            )
            session.add(collection)

        for embedding_data in data.get("embeddings", []):
            vector_values: Iterable[float] = embedding_data.get("embedding", [])
            embedding = embedding_store_cls(
                id=embedding_data["id"],
                collection_id=uuid_module.UUID(embedding_data["collection_id"]),
                embedding=list(vector_values),
                document=embedding_data.get("document"),
                cmetadata=embedding_data.get("cmetadata"),
            )
            session.add(embedding)

        session.commit()


def _restore_documents_directory(config: Config, extracted_root: Path) -> None:
    """Restore the document storage directory from the extracted archive."""

    source_dir = extracted_root / DOCUMENTS_DIRNAME
    target_dir = config.get_document_storage_path()

    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    if source_dir.exists():
        shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)


def run_restore(config: Config, archive_path: Path) -> None:
    """Restore database and document contents from a backup archive.

    The archive must have been produced by :func:`assistant.export.run_export`.

    Args:
        config: Application configuration instance.
        archive_path: Path to the ``.tar.gz`` archive to restore from.
    """

    archive_path = archive_path.resolve()
    if not archive_path.exists():
        msg = f"Archive file does not exist: {archive_path}"
        raise FileNotFoundError(msg)

    engine = get_engine()

    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)

        # 1. Extract archive contents.
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(path=tmp_dir)

        logical_data_path = tmp_dir / LOGICAL_DATA_FILENAME
        if not logical_data_path.exists():
            msg = f"Logical data file not found in archive: {LOGICAL_DATA_FILENAME}"
            raise FileNotFoundError(msg)

        data = _load_import_data(logical_data_path)

        # 2. Recreate application schema and, when applicable, vector tables.
        drop_database(engine)
        init_database(engine)
        _reset_vector_tables(engine)

        # 3. Restore ORM-managed data.
        session_factory = sessionmaker(bind=engine)
        with session_factory() as session:
            _clear_application_data(session)
            _restore_application_data(session, data)
            session.commit()

        # 4. Restore vector data (if relevant for the current backend).
        _restore_vector_data(engine, data)

        # 5. Restore documents directory.
        _restore_documents_directory(config, tmp_dir)

