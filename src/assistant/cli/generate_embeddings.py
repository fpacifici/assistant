"""CLI script to generate embeddings for a document by UUID."""

import argparse
import logging
import sys
import uuid as uuid_module

from assistant.adapters.content import DocumentContent, read_content
from assistant.agents.infra import init_environment
from assistant.agents.vectors import VectorStore, embedding_content_and_metadata
from assistant.config import Config
from assistant.models.database import get_session_factory
from assistant.models.schema import Document, DocumentFormat

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    """Generate embeddings for a document identified by UUID.

    Loads the document from the database, reads its content from the filesystem,
    decodes to text (TEXT/MARKDOWN only; PDF unsupported), and calls the embed
    function with content prefixed by the document title and metadata that
    includes the document UUID and title.

    Returns:
        0 on success, 1 on error.
    """
    parser = argparse.ArgumentParser(
        description="Generate embeddings for a document by UUID",
    )
    parser.add_argument(
        "uuid",
        type=uuid_module.UUID,
        metavar="UUID",
        help="Document UUID",
    )
    args = parser.parse_args()

    document_uuid = args.uuid

    init_environment()

    try:
        config = Config()
        storage_path = config.get_document_storage_path()
    except ValueError:
        logger.exception("Configuration error")
        return 1

    session_factory = get_session_factory()
    with session_factory() as session:
        document = session.get(Document, document_uuid)
        if document is None:
            logger.error("Document not found: %s", document_uuid)
            return 1

        if document.format == DocumentFormat.PDF:
            logger.error("PDF format is not supported for embedding")
            return 1

        content = read_content(storage_path, document.uuid)
        if content is None:
            logger.error("Content not found for document %s", document_uuid)
            return 1

        doc_content = DocumentContent(
            uuid=document.uuid,
            bytes=content.bytes,
            title=document.title,
            metadata=document.metadata_dict,
        )
        try:
            embedding_text, embedding_metadata = embedding_content_and_metadata(
                doc_content,
                extra_metadata={"uuid": str(document.uuid)},
            )
        except UnicodeDecodeError:
            logger.exception("Failed to decode content as UTF-8")
            return 1

        store = VectorStore()
        vectors = store.embed(embedding_text, embedding_metadata)
        logger.info(
            "Generated %d embedding(s) for document %s",
            len(vectors),
            document_uuid,
        )
        return 0


if __name__ == "__main__":
    sys.exit(main())
