"""External source interface definition."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from assistant.adapters.content import DocumentContent


class ExternalSource(ABC):
    """Abstract base class for external source implementations.

    Each external source plugin must extend this class and implement
    the abstract methods to provide a unified interface for fetching
    documents from external systems.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize the external source implementation.

        Args:
            config: Provider-specific configuration dictionary.
        """
        self._config = config

    @abstractmethod
    def get_document(self, external_id: str) -> DocumentContent:
        """Fetch a document by its external ID.

        Args:
            external_id: The ID of the document in the external source.

        Returns:
            DocumentContent containing the document data.

        Raises:
            DocumentNotFoundError: If the document doesn't exist.
            ExternalSourceError: For other external source errors.
        """
        ...

    @abstractmethod
    def list_documents(
        self,
        since: datetime,
        query_params: dict[str, Any],
    ) -> list[str]:
        """List document IDs updated since a given datetime.

        Args:
            since: The earliest datetime to fetch documents from.
                Documents are filtered by update date, not creation date.
            query_params: Source-specific query parameters.

        Returns:
            List of external document IDs.

        Raises:
            ExternalSourceError: If the operation fails.
        """
        ...
