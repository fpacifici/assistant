"""DataLoad job for synchronizing documents from external sources."""

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from assistant.adapters.content import write_content
from assistant.adapters.registry import Registry, get_registry
from assistant.adapters.source import ExternalSource as ExternalSourceBase
from assistant.config import Config
from assistant.models.database import get_session_factory
from assistant.models.schema import Document, DocumentFormat, ExternalSource

logger = logging.getLogger(__name__)


def load_data(config: Config | None = None) -> None:
    """Load data from all configured external sources.

    This function:
    1. Iterates through all ExternalSource instances in the database
    2. Finds the most recent document per source
    3. Fetches new/updated documents from each source
    4. Stores documents in database and filesystem
    5. Verifies and removes deleted documents

    Args:
        config: Configuration instance. If None, creates a new one.
    """
    if config is None:
        config = Config()

    registry = get_registry()
    session_factory = get_session_factory()
    storage_path = config.get_document_storage_path()

    with session_factory() as session:
        # Get all external sources from database
        external_sources = session.query(ExternalSource).all()

        if not external_sources:
            logger.warning("No external sources configured in database")
            return

        for external_source in external_sources:
            try:
                _load_source_data(
                    session=session,
                    external_source=external_source,
                    registry=registry,
                    storage_path=storage_path,
                )
            except Exception:
                logger.exception(
                    "Error loading data from source %s",
                    external_source.id,
                )

        # Verify and remove deleted documents
        _remove_deleted_documents(session, storage_path)


def _load_source_data(
    session: Session,
    external_source: ExternalSource,
    registry: Registry,
    storage_path: Path,
) -> None:
    """Load data from a single external source.

    Args:
        session: Database session.
        external_source: ExternalSource database record.
        registry: Provider registry.
        storage_path: Path to document storage directory.
    """
    logger.info("Loading data from source: %s", external_source.provider)

    # Get the most recent document update time for this source
    most_recent = (
        session.query(Document.last_update_datetime)
        .filter(Document.source_id == external_source.id)
        .order_by(Document.last_update_datetime.desc())
        .first()
    )

    since = most_recent[0] if most_recent else datetime.min.replace(tzinfo=UTC)

    # Parse provider_query as JSON if present
    query_params = {}
    if external_source.provider_query:
        import json

        try:
            query_params = json.loads(external_source.provider_query)
        except json.JSONDecodeError:
            logger.warning(
                "Invalid JSON in provider_query for source %s",
                external_source.id,
            )

    # Get provider instance
    try:
        provider = registry.get_provider(external_source.provider)
    except ValueError:
        logger.exception("Provider '%s' not found", external_source.provider)
        return

    # List documents updated since the most recent one
    try:
        external_ids = provider.list_documents(since, query_params)
    except Exception:
        logger.exception("Error listing documents from provider")
        return

    logger.info("Found %d documents to process", len(external_ids))

    # Fetch and store each document
    for external_id in external_ids:
        try:
            _process_document(
                session=session,
                external_source=external_source,
                provider=provider,
                external_id=external_id,
                storage_path=storage_path,
            )
        except Exception:
            logger.exception("Error processing document %s", external_id)


def _process_document(
    session: Session,
    external_source: ExternalSource,
    provider: ExternalSourceBase,
    external_id: str,
    storage_path: Path,
) -> None:
    """Process a single document: fetch, store, and update database.

    Args:
        session: Database session.
        external_source: ExternalSource database record.
        provider: ExternalSource provider instance.
        external_id: External document ID.
        storage_path: Path to document storage directory.
    """
    # Check if document already exists
    existing_doc = (
        session.query(Document)
        .filter(
            Document.external_id == external_id,
            Document.source_id == external_source.id,
        )
        .first()
    )

    # Fetch document content
    try:
        doc_content = provider.get_document(external_id)
    except Exception:
        logger.exception("Error fetching document %s", external_id)
        raise

    # Determine format from content (simplified - in real implementation,
    # this would be more sophisticated)
    format_str = DocumentFormat.TEXT
    if doc_content.bytes.startswith(b"%PDF"):
        format_str = DocumentFormat.PDF
    elif b"#" in doc_content.bytes[:100]:
        format_str = DocumentFormat.MARKDOWN

    now = datetime.now(UTC)

    if existing_doc:
        # Update existing document
        existing_doc.last_update_datetime = now
        existing_doc.title = f"Document {external_id}"  # Simplified
        existing_doc.format = format_str
        doc_uuid = existing_doc.uuid
        logger.debug("Updated document: %s", external_id)
    else:
        # Create new document
        doc_uuid = uuid.uuid4()
        new_doc = Document(
            uuid=doc_uuid,
            external_id=external_id,
            creation_datetime=now,
            last_update_datetime=now,
            title=f"Document {external_id}",  # Simplified
            format=format_str,
            source_id=external_source.id,
        )
        session.add(new_doc)
        logger.debug("Created document: %s", external_id)

    # Update content UUID to match document UUID
    doc_content.uuid = doc_uuid

    # Store content in filesystem
    write_content(storage_path, doc_content)

    session.commit()


def _remove_deleted_documents(_session: Session, _storage_path: Path) -> None:
    """Remove documents that no longer exist in their external sources.

    This is a simplified implementation. In a real system, we would need
    to query each external source to verify which documents still exist.

    Args:
        session: Database session.
        storage_path: Path to document storage directory.
    """
    # For now, we'll skip this step as it requires querying all external sources
    # which could be expensive. This would be implemented as:
    # 1. For each external source, get list of all current external_ids
    # 2. Find documents in DB that are not in the current list
    # 3. Delete those documents and their content files
    logger.debug("Skipping deleted document verification (not implemented)")
