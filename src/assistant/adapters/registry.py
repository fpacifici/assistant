"""Registry for external source providers."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session

from assistant.adapters.evernote import EvernoteSource
from assistant.adapters.plugins.fake import FakeExternalSource
from assistant.adapters.source import ExternalSource, ExternalSourceInstanceConfig
from assistant.config import Config
from assistant.models.schema import ExternalSource as ExternalSourceRow

logger = logging.getLogger(__name__)


class RegistryError(Exception):
    """Base exception for registry errors."""


class ProviderDisabledError(RegistryError):
    """Raised when a provider type is disabled in configuration."""

    def __init__(self, *, provider_type: str) -> None:
        """Initialize the exception.

        Args:
            provider_type: Provider type identifier that is disabled.
        """
        super().__init__(f"Provider type '{provider_type}' is disabled")


class ExternalSourceNotFoundError(RegistryError):
    """Raised when an external source instance cannot be found in the DB."""

    def __init__(self, *, source_id: UUID) -> None:
        """Initialize the exception.

        Args:
            source_id: External source instance id that could not be found.
        """
        super().__init__(f"ExternalSource id '{source_id}' not found")


class ProviderInstanceNotRegisteredError(RegistryError):
    """Raised when a provider instance is requested but not registered."""

    def __init__(self, *, source_id: UUID) -> None:
        """Initialize the exception.

        Args:
            source_id: External source instance id that is not registered.
        """
        super().__init__(
            f"ExternalSource id '{source_id}' is not registered in the registry"
        )


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
        # Provider classes are hardcoded (plugins are imported and registered here).
        # Provider *instances* are registered explicitly by calling `register(...)`.
        self._providers: dict[str, type[ExternalSource]] = {
            "fake": FakeExternalSource,
            "evernote": EvernoteSource,
        }
        self._instances: dict[UUID, ExternalSource] = {}

    def register(
        self,
        source_id: UUID,
        *,
        session: Session,
    ) -> None:
        """Register a provider instance for a specific external source id.

        Args:
            source_id: External source instance id (DB primary key).
            session: SQLAlchemy session used to load the external source row.

        Raises:
            ExternalSourceNotFoundError: If the external source instance doesn't exist.
            ProviderDisabledError: If the provider type is disabled in config.
            ValueError: If provider type is not registered or provider_query is invalid.
        """
        if source_id in self._instances:
            return

        row = self._load_external_source_row(source_id=source_id, session=session)

        provider_type = row.provider
        if provider_type not in self._providers:
            msg = f"Provider type '{provider_type}' is not registered"
            raise ValueError(msg)

        provider_config = self.config.get_external_source_config(provider_type)
        if provider_config.get("enabled") is False:
            raise ProviderDisabledError(provider_type=provider_type)

        query_params = self._parse_query_params(
            source_id=source_id, raw=row.provider_query
        )
        instance_config = ExternalSourceInstanceConfig(
            provider_config=provider_config,
            query_params=query_params,
        )

        provider_class = self._providers[provider_type]
        logger.debug("Building provider instance: %s (%s)", source_id, provider_type)
        instance = provider_class.build(instance_config)
        self._instances[source_id] = instance

    def get_provider(
        self,
        source_id: UUID,
    ) -> ExternalSource:
        """Get a registered provider instance for a specific external source id.

        Args:
            source_id: External source instance id (DB primary key).

        Returns:
            Registered ExternalSource instance for the given external source id.

        Raises:
            ProviderInstanceNotRegisteredError: If the instance has not been registered.
        """
        instance = self._instances.get(source_id)
        if instance is None:
            raise ProviderInstanceNotRegisteredError(source_id=source_id)
        return instance

    def list_providers(self) -> list[str]:
        """List all registered provider types.

        Returns:
            List of provider types.
        """
        return list(self._providers.keys())

    @staticmethod
    def _parse_query_params(*, source_id: UUID, raw: str | None) -> dict[str, object]:
        """Parse provider_query JSON from DB into a mapping."""

        if not raw:
            return {}
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            msg = f"provider_query for source {source_id} must be a JSON object"
            raise TypeError(msg)
        return cast("dict[str, object]", parsed)

    @staticmethod
    def _load_external_source_row(
        *, source_id: UUID, session: Session
    ) -> ExternalSourceRow:
        """Load the ExternalSource DB row for a given instance id."""

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
