"""Tests for registry functionality."""

import pytest
from sqlalchemy.orm import Session

from assistant.adapters.plugins.fake import FakeExternalSource
from assistant.adapters.registry import Registry, get_registry
from assistant.config import Config
from assistant.models.schema import ExternalSource


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


def test_registry_get_provider(test_config: Config, db_session: Session) -> None:
    """Test getting a provider instance."""
    registry = Registry(config=test_config)
    registry.register("fake", FakeExternalSource)

    source = ExternalSource(provider="fake", provider_query="{}")
    db_session.add(source)
    db_session.commit()

    provider = registry.get_provider(source.id, session=db_session)
    assert isinstance(provider, FakeExternalSource)


def test_registry_get_provider_is_cached(test_config: Config, db_session: Session) -> None:
    """Test that provider instances are cached by external source id."""
    registry = Registry(config=test_config)
    registry.register("fake", FakeExternalSource)

    source = ExternalSource(provider="fake", provider_query="{}")
    db_session.add(source)
    db_session.commit()

    provider1 = registry.get_provider(source.id, session=db_session)
    provider2 = registry.get_provider(source.id, session=db_session)

    assert provider1 is provider2


def test_registry_get_unregistered_provider(test_config: Config, db_session: Session) -> None:
    """Test getting an unregistered provider raises error."""
    registry = Registry(config=test_config)

    source = ExternalSource(provider="nonexistent", provider_query="{}")
    db_session.add(source)
    db_session.commit()

    with pytest.raises(ValueError, match="not registered"):
        registry.get_provider(source.id, session=db_session)


@pytest.mark.usefixtures("test_config")
def test_get_registry_singleton() -> None:
    """Test that get_registry returns a singleton."""

    # Reset the global registry
    import assistant.adapters.registry

    assistant.adapters.registry._registry = None

    registry1 = get_registry()
    registry2 = get_registry()

    assert registry1 is registry2
