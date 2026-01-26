"""Tests for registry functionality."""

import pytest
from sqlalchemy.orm import Session

import assistant.adapters.registry as registry_module
from assistant.adapters.plugins.fake import FakeExternalSource
from assistant.adapters.registry import Registry, get_registry
from assistant.config import Config
from assistant.models.schema import ExternalSource


def test_registry_creation(test_config: Config) -> None:
    """Test creating a registry."""
    registry = Registry(config=test_config)
    assert registry is not None
    assert "fake" in registry.list_providers()


def test_registry_register_provider_instance(test_config: Config, db_session: Session) -> None:
    """Test registering a provider instance."""
    registry = Registry(config=test_config)

    source = ExternalSource(provider="fake", provider_query="{}")
    db_session.add(source)
    db_session.commit()

    registry.register(source.id, session=db_session)

    provider = registry.get_provider(source.id)
    assert isinstance(provider, FakeExternalSource)


def test_registry_get_provider(test_config: Config, db_session: Session) -> None:
    """Test getting a provider instance."""
    registry = Registry(config=test_config)

    source = ExternalSource(provider="fake", provider_query="{}")
    db_session.add(source)
    db_session.commit()

    registry.register(source.id, session=db_session)
    provider = registry.get_provider(source.id)
    assert isinstance(provider, FakeExternalSource)


def test_registry_get_provider_is_cached(test_config: Config, db_session: Session) -> None:
    """Test that provider instances are cached by external source id."""
    registry = Registry(config=test_config)

    source = ExternalSource(provider="fake", provider_query="{}")
    db_session.add(source)
    db_session.commit()

    registry.register(source.id, session=db_session)
    provider1 = registry.get_provider(source.id)
    provider2 = registry.get_provider(source.id)

    assert provider1 is provider2


def test_registry_get_unregistered_provider(test_config: Config, db_session: Session) -> None:
    """Test getting an unregistered provider raises error."""
    registry = Registry(config=test_config)

    source = ExternalSource(provider="nonexistent", provider_query="{}")
    db_session.add(source)
    db_session.commit()

    with pytest.raises(ValueError, match="not registered"):
        registry.register(source.id, session=db_session)


@pytest.mark.usefixtures("test_config")
def test_get_registry_singleton() -> None:
    """Test that get_registry returns a singleton."""

    # Reset the global registry
    registry_module._registry = None

    registry1 = get_registry()
    registry2 = get_registry()

    assert registry1 is registry2
