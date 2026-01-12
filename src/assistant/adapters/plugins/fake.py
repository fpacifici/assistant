"""Fake external source implementation for testing."""

import uuid
from datetime import UTC, datetime
from typing import Any

from assistant.adapters.content import DocumentContent
from assistant.adapters.source import ExternalSource


class FakeExternalSource(ExternalSource):
    """Fake external source implementation for testing.

    Returns mock documents with predictable content for testing purposes.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize fake external source.

        Args:
            config: Configuration dictionary (not used in fake implementation).
        """
        self.config = config
        # Store mock documents
        self._documents: dict[str, tuple[datetime, bytes]] = {}
        self._initialize_mock_documents()

    def _initialize_mock_documents(self) -> None:
        """Initialize some mock documents for testing."""
        base_time = datetime.now(UTC)
        self._documents["doc1"] = (
            base_time,
            b"Mock document 1 content\nThis is a test document.",
        )
        self._documents["doc2"] = (
            base_time,
            b"Mock document 2 content\nAnother test document with more text.",
        )

    def get_document(self, external_id: str) -> DocumentContent:
        """Fetch a mock document by external ID.

        Args:
            external_id: The ID of the document.

        Returns:
            DocumentContent containing mock document data.

        Raises:
            ValueError: If the document doesn't exist.
        """
        if external_id not in self._documents:
            msg = f"Document '{external_id}' not found"
            raise ValueError(msg)

        # Generate a deterministic UUID from the external_id
        doc_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, f"fake:{external_id}")
        _, content_bytes = self._documents[external_id]

        return DocumentContent(uuid=doc_uuid, bytes=content_bytes)

    def list_documents(
        self,
        since: datetime,
        query_params: dict[str, Any],  # noqa: ARG002
    ) -> list[str]:
        """List mock document IDs updated since a given datetime.

        Args:
            since: The earliest datetime to fetch documents from.
            query_params: Source-specific query parameters (not used).

        Returns:
            List of external document IDs.
        """
        result = []
        # Ensure both datetimes are timezone-aware for comparison
        if since.tzinfo is None:
            # If since is naive, make it timezone-aware (UTC)
            since = since.replace(tzinfo=UTC)

        for external_id, (update_time_raw, _) in self._documents.items():
            # Ensure update_time is timezone-aware
            update_time = update_time_raw
            if update_time.tzinfo is None:
                update_time = update_time.replace(tzinfo=UTC)
            if update_time >= since:
                result.append(external_id)
        return result
