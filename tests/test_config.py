"""Tests for configuration management."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from assistant.config import Config

_CONFIG_ENV_KEYS: tuple[str, ...] = (
    "DOCUMENT_STORAGE_PATH",
    "DATABASE_URL",
    "DATABASE_HOST",
    "DATABASE_PORT",
    "DATABASE_USER",
    "DATABASE_PASSWORD",
    "DATABASE_NAME",
    "EXTERNAL_SOURCES_FAKE_ENABLED",
    "EXTERNAL_SOURCES_FAKE_TIMEOUT",
)


@pytest.fixture(autouse=True)
def _clear_config_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure config-related env vars don't leak between tests."""

    for key in _CONFIG_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_config_loads_from_file(tmp_path: Path) -> None:
    """Test loading configuration from YAML file."""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(
        "document_storage_path: /test/path\n"
        "external_sources:\n"
        "  fake:\n"
        "    enabled: true\n",
    )

    config = Config(config_path=config_file)

    assert config.get("document_storage_path") == "/test/path"
    assert config.get("external_sources.fake.enabled") is True


def test_config_handles_missing_file(tmp_path: Path) -> None:
    """Test that config handles missing file gracefully."""
    config_file = tmp_path / "nonexistent.yaml"
    config = Config(config_path=config_file)

    # Should return default value
    assert config.get("some_key", "default") == "default"


def test_config_get_with_dot_notation(tmp_path: Path) -> None:
    """Test getting nested config values with dot notation."""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(
        "external_sources:\n  fake:\n    enabled: true\n    timeout: 30\n",
    )

    config = Config(config_path=config_file)

    assert config.get("external_sources.fake.enabled") is True
    assert config.get("external_sources.fake.timeout") == 30


def test_config_get_document_storage_path(tmp_path: Path) -> None:
    """Test getting document storage path."""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text("document_storage_path: /custom/path\n")

    config = Config(config_path=config_file)
    path = config.get_document_storage_path()

    assert path == Path("/custom/path").resolve()


def test_config_get_document_storage_path_env_override(tmp_path: Path) -> None:
    """Test that DOCUMENT_STORAGE_PATH env var overrides config."""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text("document_storage_path: /config/path\n")

    config = Config(config_path=config_file)

    with patch.dict(os.environ, {"DOCUMENT_STORAGE_PATH": "/env/path"}):
        path = config.get_document_storage_path()
        assert path == Path("/env/path").resolve()


def test_config_get_external_source_config(tmp_path: Path) -> None:
    """Test getting external source configuration."""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(
        "external_sources:\n"
        "  fake:\n"
        "    enabled: true\n"
        "    timeout: 30\n"
        "  other:\n"
        "    enabled: false\n",
    )

    config = Config(config_path=config_file)

    fake_config = config.get_external_source_config("fake")
    assert fake_config["enabled"] is True
    assert fake_config["timeout"] == 30

    other_config = config.get_external_source_config("other")
    assert other_config["enabled"] is False

    missing_config = config.get_external_source_config("nonexistent")
    assert missing_config == {}


def test_config_get_database_config_from_components(tmp_path: Path) -> None:
    """Test getting database config components from YAML."""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(
        "database:\n"
        "  host: testhost\n"
        "  port: 5433\n"
        "  user: testuser\n"
        "  password: testpass\n"
        "  name: testdb\n",
    )

    config = Config(config_path=config_file)
    db_config = config.get_database_config()

    assert db_config == {
        "host": "testhost",
        "port": 5433,
        "user": "testuser",
        "password": "testpass",
        "name": "testdb",
    }


def test_config_get_database_config_from_env_url(tmp_path: Path) -> None:
    """Test that DATABASE_URL env var yields url-only database config."""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(
        "database:\n"
        "  host: confighost\n"
        "  port: 5432\n"
        "  user: configuser\n"
        "  password: configpass\n"
        "  name: configdb\n",
    )

    config = Config(config_path=config_file)

    env_url = "postgresql://envuser:envpass@envhost:5434/envdb"
    with patch.dict(os.environ, {"DATABASE_URL": env_url}):
        assert config.get_database_config() == {"url": env_url}


def test_config_get_database_config_missing_config(tmp_path: Path) -> None:
    """Test that missing database config raises ValueError."""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text("other_key: value\n")

    config = Config(config_path=config_file)

    with pytest.raises(ValueError, match="Database configuration not found"):
        config.get_database_config()


def test_config_get_database_config_has_no_defaults(tmp_path: Path) -> None:
    """Test that get_database_config does not apply defaults for missing keys."""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(
        "database:\n  host: customhost\n  name: customdb\n",
    )

    config = Config(config_path=config_file)
    with pytest.raises(ValueError, match="missing required keys"):
        _ = config.get_database_config()


def test_config_get_env_override_even_when_key_exists(tmp_path: Path) -> None:
    """Test that env vars override YAML even when YAML key exists."""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text("document_storage_path: /config/path\n")

    config = Config(config_path=config_file)

    with patch.dict(os.environ, {"DOCUMENT_STORAGE_PATH": "/env/path"}):
        assert config.get("document_storage_path") == "/env/path"


def test_config_get_external_sources_env_override_type_coercion(tmp_path: Path) -> None:
    """Test type coercion for env overrides (bool/int)."""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(
        "external_sources:\n  fake:\n    enabled: true\n    timeout: 30\n",
    )

    config = Config(config_path=config_file)

    with patch.dict(
        os.environ,
        {"EXTERNAL_SOURCES_FAKE_ENABLED": "false", "EXTERNAL_SOURCES_FAKE_TIMEOUT": "31"},
    ):
        assert config.get("external_sources.fake.enabled") is False
        assert config.get("external_sources.fake.timeout") == 31


def test_config_get_database_config_from_database_url_key(tmp_path: Path) -> None:
    """Test that database.url in YAML is used as the connection string."""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(
        "database:\n  url: postgresql://yamluser:yamlpass@yamlhost:5432/yamldb\n",
    )

    config = Config(config_path=config_file)
    assert config.get_database_config() == {
        "url": "postgresql://yamluser:yamlpass@yamlhost:5432/yamldb",
    }


def test_config_get_database_config_overridden(tmp_path: Path) -> None:
    """Test that get_database_config returns an overridden TypedDict."""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(
        "database:\n"
        "  host: confighost\n"
        "  port: 5432\n"
        "  user: configuser\n"
        "  password: configpass\n"
        "  name: configdb\n",
    )

    config = Config(config_path=config_file)

    with patch.dict(os.environ, {"DATABASE_HOST": "envhost", "DATABASE_PORT": "5434"}):
        db_config = config.get_database_config()
        assert db_config["host"] == "envhost"
        assert db_config["port"] == 5434
        assert db_config["user"] == "configuser"
        assert db_config["name"] == "configdb"


def test_config_get_database_config_env_components_without_yaml(tmp_path: Path) -> None:
    """Test that env-only database configuration works without YAML section."""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text("other_key: value\n")

    config = Config(config_path=config_file)

    with patch.dict(
        os.environ,
        {
            "DATABASE_HOST": "envhost",
            "DATABASE_PORT": "5433",
            "DATABASE_USER": "envuser",
            "DATABASE_PASSWORD": "envpass",
            "DATABASE_NAME": "envdb",
        },
    ):
        assert config.get_database_config() == {
            "host": "envhost",
            "port": 5433,
            "user": "envuser",
            "password": "envpass",
            "name": "envdb",
        }


def test_config_env_override_invalid_int_raises(tmp_path: Path) -> None:
    """Test that invalid int env overrides raise ValueError."""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text("database:\n  port: 5432\n")

    config = Config(config_path=config_file)

    with (
        patch.dict(os.environ, {"DATABASE_PORT": "not-an-int"}),
        pytest.raises(ValueError, match="Invalid int"),
    ):
        _ = config.get("database.port", 5432)
