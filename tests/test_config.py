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
    "DOMAIN",
    "MAILGUN_APIURL",
    "MAILGUN_APIKEY",
    "MAILGUN_SENDER",
    "MAILGUN_TIMEOUT",
    "PORT",
    "REGISTRATION_REGISTRATION_ENABLED",
    "REGISTRATION_INVITES_ENABLED",
    "REGISTRATION_DEFAULT_QUOTA",
    "REGISTRATION_EXPIRY_DAYS",
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


def test_config_get_domain(tmp_path: Path) -> None:
    """Test getting the assistant's configured domain."""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text("domain: mg.example.com\n")

    config = Config(config_path=config_file)
    assert config.get_domain() == "mg.example.com"


def test_config_get_domain_env_override(tmp_path: Path) -> None:
    """Test that DOMAIN env var overrides YAML domain."""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text("domain: mg.example.com\n")

    config = Config(config_path=config_file)

    with patch.dict(os.environ, {"DOMAIN": "mg.env.com"}):
        assert config.get_domain() == "mg.env.com"


def test_config_get_domain_missing_raises(tmp_path: Path) -> None:
    """Test that missing domain (YAML and env) raises ValueError."""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text("other_key: value\n")

    config = Config(config_path=config_file)

    with pytest.raises(ValueError, match="Domain configuration not found"):
        config.get_domain()


def test_config_get_mailgun_config_from_yaml(tmp_path: Path) -> None:
    """Test getting Mailgun config with all fields present in YAML."""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(
        "mailgun:\n"
        "  apiurl: https://api.mailgun.net/v3\n"
        "  apikey: key-123\n"
        "  sender: noreply@example.com\n"
        "  timeout: 20\n",
    )

    config = Config(config_path=config_file)
    assert config.get_mailgun_config() == {
        "apiurl": "https://api.mailgun.net/v3",
        "apikey": "key-123",
        "sender": "noreply@example.com",
        "timeout": 20,
    }


def test_config_get_mailgun_config_timeout_defaults(tmp_path: Path) -> None:
    """Test that timeout defaults to 10 when absent from YAML and env."""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(
        "mailgun:\n"
        "  apiurl: https://api.mailgun.net/v3\n"
        "  apikey: key-123\n"
        "  sender: noreply@example.com\n",
    )

    config = Config(config_path=config_file)
    assert config.get_mailgun_config()["timeout"] == 10


@pytest.mark.parametrize("missing_field", ["apiurl", "apikey", "sender"])
def test_config_get_mailgun_config_missing_required_field_raises(
    tmp_path: Path, missing_field: str
) -> None:
    """Test that each individually missing required Mailgun field raises ValueError."""
    fields = {
        "apiurl": "https://api.mailgun.net/v3",
        "apikey": "key-123",
        "sender": "noreply@example.com",
    }
    del fields[missing_field]

    config_file = tmp_path / "test_config.yaml"
    body = "\n".join(f"  {key}: {value}" for key, value in fields.items())
    config_file.write_text(f"mailgun:\n{body}\n")

    config = Config(config_path=config_file)

    with pytest.raises(ValueError, match=missing_field):
        config.get_mailgun_config()


def test_config_get_mailgun_config_env_overrides(tmp_path: Path) -> None:
    """Test that MAILGUN_* env vars override YAML Mailgun config."""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(
        "mailgun:\n"
        "  apiurl: https://api.mailgun.net/v3\n"
        "  apikey: key-123\n"
        "  sender: noreply@example.com\n"
        "  timeout: 20\n",
    )

    config = Config(config_path=config_file)

    with patch.dict(
        os.environ,
        {
            "MAILGUN_APIURL": "https://api.eu.mailgun.net/v3",
            "MAILGUN_APIKEY": "env-key",
            "MAILGUN_SENDER": "env@example.com",
            "MAILGUN_TIMEOUT": "5",
        },
    ):
        assert config.get_mailgun_config() == {
            "apiurl": "https://api.eu.mailgun.net/v3",
            "apikey": "env-key",
            "sender": "env@example.com",
            "timeout": 5,
        }


def test_config_get_mailgun_config_env_only_without_yaml(tmp_path: Path) -> None:
    """Test that env-only Mailgun configuration works without a YAML section."""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text("other_key: value\n")

    config = Config(config_path=config_file)

    with patch.dict(
        os.environ,
        {
            "MAILGUN_APIURL": "https://api.mailgun.net/v3",
            "MAILGUN_APIKEY": "env-key",
            "MAILGUN_SENDER": "env@example.com",
        },
    ):
        assert config.get_mailgun_config() == {
            "apiurl": "https://api.mailgun.net/v3",
            "apikey": "env-key",
            "sender": "env@example.com",
            "timeout": 10,
        }


def test_config_get_port_defaults(tmp_path: Path) -> None:
    """Test that get_port defaults to 8000 when absent from YAML and env."""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text("other_key: value\n")

    config = Config(config_path=config_file)
    assert config.get_port() == 8000


def test_config_get_port_from_yaml(tmp_path: Path) -> None:
    """Test getting the configured port from YAML."""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text("port: 9000\n")

    config = Config(config_path=config_file)
    assert config.get_port() == 9000


def test_config_get_port_env_override(tmp_path: Path) -> None:
    """Test that PORT env var overrides YAML port."""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text("port: 9000\n")

    config = Config(config_path=config_file)

    with patch.dict(os.environ, {"PORT": "9001"}):
        assert config.get_port() == 9001


def test_config_get_use_https_defaults(tmp_path: Path) -> None:
    """Test that get_use_https defaults to True when absent from YAML and env."""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text("other_key: value\n")

    config = Config(config_path=config_file)
    assert config.get_use_https() is True


def test_config_get_use_https_from_yaml(tmp_path: Path) -> None:
    """Test getting the configured use_https flag from YAML."""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text("use_https: false\n")

    config = Config(config_path=config_file)
    assert config.get_use_https() is False


def test_config_get_use_https_env_override(tmp_path: Path) -> None:
    """Test that USE_HTTPS env var overrides YAML use_https."""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text("use_https: true\n")

    config = Config(config_path=config_file)

    with patch.dict(os.environ, {"USE_HTTPS": "false"}):
        assert config.get_use_https() is False


def test_config_get_registration_config_defaults(tmp_path: Path) -> None:
    """Test that get_registration_config returns documented defaults when absent."""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text("other_key: value\n")

    config = Config(config_path=config_file)
    assert config.get_registration_config() == {
        "registration_enabled": True,
        "invites_enabled": True,
        "default_quota": 5,
        "expiry_days": 1,
    }


def test_config_get_registration_config_from_yaml(tmp_path: Path) -> None:
    """Test getting registration config from YAML."""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(
        "registration:\n"
        "  registration_enabled: false\n"
        "  invites_enabled: false\n"
        "  default_quota: 3\n"
        "  expiry_days: 2\n",
    )

    config = Config(config_path=config_file)
    assert config.get_registration_config() == {
        "registration_enabled": False,
        "invites_enabled": False,
        "default_quota": 3,
        "expiry_days": 2,
    }


@pytest.mark.parametrize(
    ("env_key", "env_value", "field", "expected"),
    [
        ("REGISTRATION_REGISTRATION_ENABLED", "false", "registration_enabled", False),
        ("REGISTRATION_INVITES_ENABLED", "false", "invites_enabled", False),
        ("REGISTRATION_DEFAULT_QUOTA", "7", "default_quota", 7),
        ("REGISTRATION_EXPIRY_DAYS", "3", "expiry_days", 3),
    ],
)
def test_config_get_registration_config_env_overrides(
    tmp_path: Path, env_key: str, env_value: str, field: str, expected: object
) -> None:
    """Test that each registration config key is individually env-overridable."""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text("other_key: value\n")

    config = Config(config_path=config_file)

    with patch.dict(os.environ, {env_key: env_value}):
        assert config.get_registration_config()[field] == expected  # type: ignore[literal-required]
