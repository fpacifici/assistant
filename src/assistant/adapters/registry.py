"""Registry for external source providers."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session

from assistant.adapters.source import ExternalSource, ExternalSourceInstanceConfig
from assistant.config import Config
from assistant.models.database import get_session_factory
from assistant.models.schema import ExternalSource as ExternalSourceRow

logger = logging.getLogger(__name__)


class ProviderDisabledError(RuntimeError):
    """Raised when a provider type is disabled in configuration."""

    def __init__(self, *, provider_type: str) -> None:
        """Initialize the exception.

        Args:
            provider_type: Provider type identifier that is disabled.
        """
        super().__init__(f"Provider type '{provider_type}' is disabled")


class ExternalSourceNotFoundError(RuntimeError):
    """Raised when an external source instance cannot be found in the DB."""

    def __init__(self, *, source_id: uuid.UUID) -> None:
        """Initialize the exception.

        Args:
            source_id: External source instance id that could not be found.
        """
        super().__init__(f"ExternalSource id '{source_id}' not found")


class Registry:
    """Registry for mapping provider types to implementations and caching instances.

    The registry maps provider *types* (e.g. "evernote") to their plugin classes.
    It returns cached, configured instances keyed by the DB `ExternalSource.id`
    (instance id), binding DB query params at instantiation time.
    """

    def __init__(self, config: Config | None = None) -> None:
        """Initialize the registry.

        Args:
            config: Configuration instance. If None, creates a new one.
        """
        self.config = config or Config()
        self._providers: dict[str, type[ExternalSource]] = {}
        self._instances: dict[uuid.UUID, ExternalSource] = {}

    def register(
        self,
        provider_type: str,
        provider_class: type[ExternalSource],
    ) -> None:
        """Register a provider implementation.

        Args:
            provider_type: Provider type identifier (e.g. "evernote", "fake").
            provider_class: Class that implements ExternalSource.
        """
        self._providers[provider_type] = provider_class
        logger.debug("Registered provider type: %s", provider_type)

    def get_provider(
        self, source_id: uuid.UUID, *, session: Session | None = None
    ) -> ExternalSource:
        """Get a configured instance for a specific external source id.

        Args:
            source_id: External source instance id (DB primary key).
            session: Optional SQLAlchemy Session to use. If omitted, a short-lived session is
                created internally.

        Returns:
            Cached ExternalSource instance configured for the given external source id.

        Raises:
            ExternalSourceNotFoundError: If the external source instance doesn't exist.
            ProviderDisabledError: If the provider type is disabled in config.
            ValueError: If the provider type is not registered.
        """
        if source_id in self._instances:
            return self._instances[source_id]

        row = self._load_external_source_row(source_id=source_id, session=session)

        provider_type = row.provider
        if provider_type not in self._providers:
            msg = f"Provider type '{provider_type}' is not registered"
            raise ValueError(msg)

        provider_config = self.config.get_external_source_config(provider_type)
        if provider_config.get("enabled") is False:
            raise ProviderDisabledError(provider_type=provider_type)

        query_params = self._parse_query_params(source_id=source_id, raw=row.provider_query)
        instance_config = ExternalSourceInstanceConfig(
            provider_config=provider_config,
            query_params=query_params,
        )

        provider_class = self._providers[provider_type]
        logger.debug("Creating provider instance: %s (%s)", source_id, provider_type)
        instance = provider_class(instance_config)
        self._instances[source_id] = instance
        return instance

    def list_providers(self) -> list[str]:
        """List all registered provider types.

        Returns:
            List of provider types.
        """
        return list(self._providers.keys())

    @staticmethod
    def _parse_query_params(*, source_id: uuid.UUID, raw: str | None) -> dict[str, object]:
        """Parse provider_query JSON from DB into a mapping."""

        if not raw:
            return {}
        try:
            parsed: Any = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON in provider_query for source %s", source_id)
            return {}
        if not isinstance(parsed, dict):
            logger.warning("provider_query for source %s must be a JSON object", source_id)
            return {}
        # Ensure keys are strings (JSON object keys are strings by spec, but validate defensively).
        result: dict[str, object] = {}
        for key, value in parsed.items():
            if isinstance(key, str):
                result[key] = value
        return result

    @staticmethod
    def _load_external_source_row(
        *, source_id: uuid.UUID, session: Session | None
    ) -> ExternalSourceRow:
        """Load the ExternalSource DB row for a given instance id."""

        if session is None:
            session_factory = get_session_factory()
            with session_factory() as db_session:
                row = db_session.get(ExternalSourceRow, source_id)
        else:
            row = session.get(ExternalSourceRow, source_id)

        if row is None:
            raise ExternalSourceNotFoundError(source_id=source_id)
        return row


# Global registry instance
_registry: Registry | None = None


def get_registry() -> Registry:
    """Get the global registry instance.

    Returns:
        Global Registry instance.
    """
    global _registry  # noqa: PLW0603
    if _registry is None:
        _registry = Registry()
    return _registry
