"""Registry for external source providers."""

import logging

from assistant.adapters.source import ExternalSource
from assistant.config import Config

logger = logging.getLogger(__name__)


class Registry:
    """Registry for mapping provider IDs to ExternalSource implementations.

    The registry loads YAML configuration for providers and returns
    configured instances of ExternalSource implementations.
    """

    def __init__(self, config: Config | None = None) -> None:
        """Initialize the registry.

        Args:
            config: Configuration instance. If None, creates a new one.
        """
        self.config = config or Config()
        self._providers: dict[str, type[ExternalSource]] = {}

    def register(
        self,
        provider_id: str,
        provider_class: type[ExternalSource],
    ) -> None:
        """Register a provider implementation.

        Args:
            provider_id: Unique identifier for the provider.
            provider_class: Class that implements ExternalSource.
        """
        self._providers[provider_id] = provider_class
        logger.debug("Registered provider: %s", provider_id)

    def get_provider(self, provider_id: str) -> ExternalSource:
        """Get a configured instance of a provider.

        Args:
            provider_id: Identifier of the provider.

        Returns:
            Configured ExternalSource instance.

        Raises:
            ValueError: If the provider is not registered.
        """
        if provider_id not in self._providers:
            msg = f"Provider '{provider_id}' is not registered"
            raise ValueError(msg)

        provider_class = self._providers[provider_id]
        provider_config = self.config.get_external_source_config(provider_id)

        logger.debug("Creating instance of provider: %s", provider_id)
        return provider_class(provider_config)

    def list_providers(self) -> list[str]:
        """List all registered provider IDs.

        Returns:
            List of provider IDs.
        """
        return list(self._providers.keys())


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
