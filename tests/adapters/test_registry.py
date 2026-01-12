"""Tests for registry functionality."""

import pytest

from assistant.adapters.plugins.fake import FakeExternalSource
from assistant.adapters.registry import Registry, get_registry
from assistant.config import Config


def test_registry_creation(test_config: Config) -> None:
    """Test creating a registry."""
    registry = Registry(config=test_config)
    assert registry is not None
    assert len(registry.list_providers()) == 0


def test_registry_register_provider(test_config: Config) -> None:
    """Test registering a provider."""
    registry = Registry(config=test_config)
    registry.register("fake", FakeExternalSource)

    assert "fake" in registry.list_providers()


def test_registry_get_provider(test_config: Config) -> None:
    """Test getting a provider instance."""
    registry = Registry(config=test_config)
    registry.register("fake", FakeExternalSource)

    provider = registry.get_provider("fake")
    assert isinstance(provider, FakeExternalSource)


def test_registry_get_unregistered_provider(test_config: Config) -> None:
    """Test getting an unregistered provider raises error."""
    registry = Registry(config=test_config)

    with pytest.raises(ValueError, match="not registered"):
        registry.get_provider("nonexistent")


@pytest.mark.usefixtures("test_config")
def test_get_registry_singleton() -> None:
    """Test that get_registry returns a singleton."""

    # Reset the global registry
    import assistant.adapters.registry

    assistant.adapters.registry._registry = None

    registry1 = get_registry()
    registry2 = get_registry()

    assert registry1 is registry2
