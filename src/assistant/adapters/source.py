"""External source interface definition."""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Self

from assistant.adapters.content import DocumentContent


@dataclass(frozen=True, slots=True)
class ExternalSourceInstanceConfig:
    """Configuration for a single ExternalSource instance.

    This is the resolved configuration used to instantiate a provider plugin for a specific
    configured external source (e.g. Evernote notebook A vs Evernote notebook B).

    Attributes:
        provider_config: Provider-type configuration loaded from YAML (e.g. credentials, timeouts).
        query_params: Source-instance query parameters loaded from the DB (`provider_query` JSON).
    """

    provider_config: Mapping[str, object]
    query_params: Mapping[str, object]


class ExternalSource(ABC):
    """Abstract base class for external source implementations.

    Each external source plugin must extend this class and implement
    the abstract methods to provide a unified interface for fetching
    documents from external systems.
    """

    def __init__(self, config: ExternalSourceInstanceConfig) -> None:
        """Initialize the external source implementation.

        Args:
            config: Instance configuration (provider config + DB query params).
        """
        self._config = config

    @classmethod
    @abstractmethod
    def build(cls, config: ExternalSourceInstanceConfig) -> Self:
        """Build an ExternalSource instance from resolved instance config.

        Plugins must implement this factory method instead of relying on a shared constructor
        contract across implementations.

        Args:
            config: Instance configuration (provider config + DB query params).

        Returns:
            A configured ExternalSource instance.
        """
        ...

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
    ) -> list[str]:
        """List document IDs updated since a given datetime.

        Args:
            since: The earliest datetime to fetch documents from.
                Documents are filtered by update date, not creation date.

        Returns:
            List of external document IDs.

        Raises:
            ExternalSourceError: If the operation fails.
        """
        ...

    def get_document_metadata(self, external_id: str) -> dict[str, str]:
        """Return provider-specific metadata for a document.

        Implementations may override this to expose additional metadata such as titles,
        notebook names, or timestamps. The default implementation returns an empty
        mapping, indicating that no metadata is available.

        Args:
            external_id: The ID of the document in the external source.

        Returns:
            A dictionary mapping metadata keys to values for the given document.
        """
        # Default implementation so providers can opt in without breaking callers.
        del external_id  # Unused in the base implementation.
        return {}
