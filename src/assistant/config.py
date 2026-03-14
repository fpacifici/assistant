"""Configuration management for the assistant package.

This module loads configuration from YAML and supports environment-variable overrides.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TypedDict, TypeVar, cast, overload

import yaml

_MISSING: object = object()


class DatabaseUrlConfig(TypedDict):
    """Database configuration that provides a full connection URL."""

    url: str


class DatabaseComponentsConfig(TypedDict):
    """Database configuration expressed as connection components."""

    host: str
    port: int
    user: str
    password: str
    name: str


DatabaseConfig = DatabaseUrlConfig | DatabaseComponentsConfig


class ExternalSourceProviderConfig(TypedDict, total=False):
    """External source provider configuration.

    Provider configurations are plugin-specific; this type captures common fields.
    """

    enabled: bool
    timeout: int


ExternalSourcesConfig = dict[str, ExternalSourceProviderConfig]


class AssistantConfig(TypedDict, total=False):
    """Top-level configuration structure loaded from YAML."""

    database: DatabaseConfig
    document_storage_path: str
    external_sources: ExternalSourcesConfig


T = TypeVar("T")


def _env_var_name(key: str) -> str:
    """Convert a dotted config key into an environment variable name.

    Examples:
        - "database.url" -> "DATABASE_URL"
        - "external_sources.fake.enabled" -> "EXTERNAL_SOURCES_FAKE_ENABLED"
    """

    return key.upper().replace(".", "_")


def _coerce_env_value(
    *, key: str, env_key: str, raw: str, expected_type: type[object]
) -> object:
    """Coerce an environment variable string to an expected scalar type.

    Args:
        key: Config key being overridden.
        env_key: Environment variable name.
        raw: Raw env var value.
        expected_type: Expected Python type (bool/int/float/str).

    Returns:
        The coerced value.

    Raises:
        ValueError: If coercion fails or the type is unsupported.
    """

    if expected_type is str:
        return raw
    if expected_type is bool:
        normalized = raw.strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
        msg = f"Invalid boolean for {env_key} overriding {key!r}: {raw!r}"
        raise ValueError(msg)
    if expected_type is int:
        try:
            return int(raw.strip())
        except ValueError as exc:  # pragma: no cover
            msg = f"Invalid int for {env_key} overriding {key!r}: {raw!r}"
            raise ValueError(msg) from exc
    if expected_type is float:
        try:
            return float(raw.strip())
        except ValueError as exc:  # pragma: no cover
            msg = f"Invalid float for {env_key} overriding {key!r}: {raw!r}"
            raise ValueError(msg) from exc

    msg = (
        f"Unsupported env override type for {env_key} overriding {key!r}: "
        f"expected {expected_type.__name__}"
    )
    raise ValueError(msg)


class Config:
    """Configuration manager for the assistant application.

    Loads configuration from YAML file and supports environment variable overrides.
    """

    def __init__(self, config_path: Path | str | None = None) -> None:
        """Initialize configuration.

        Args:
            config_path: Path to YAML config file. If None, looks for config.yaml
                in the project root.
        """
        if config_path is None:
            # Look for config.yaml in project root
            project_root = Path(__file__).resolve().parents[2]
            config_path = project_root / "config.yaml"
        else:
            config_path = Path(config_path)

        self.config_path = config_path
        self._config: AssistantConfig = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from YAML file."""
        if not self.config_path.exists():
            self._config = {}
            return

        with self.config_path.open(encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}

        if not isinstance(loaded, dict):
            self._config = {}
            return

        # We load YAML dynamically; typing is enforced at the access boundaries.
        self._config = cast("AssistantConfig", loaded)

    def _get_from_config(self, key: str) -> object:
        """Get a value from the YAML config without env-var overrides."""

        keys = key.split(".")
        value: object = self._config
        for part in keys:
            if not isinstance(value, dict) or part not in value:
                return _MISSING
            value = value[part]
        return value

    def _get_expected_scalar_type(
        self, *, key: str, default: object | None
    ) -> type[object]:
        """Infer the expected scalar type for an env override.

        Preference order:
        1) The type of the YAML value (if present and scalar)
        2) The type of the provided default (if scalar)
        3) str (fallback)
        """

        yaml_value = self._get_from_config(key)
        if yaml_value is not _MISSING and yaml_value is not None:
            yaml_type = type(yaml_value)
            if yaml_type in {bool, int, float, str}:
                return yaml_type

        if default is not None:
            default_type = type(default)
            if default_type in {bool, int, float, str}:
                return default_type

        return str

    def _get_typed_value(self, *, key: str, expected_type: type[T]) -> T | None:
        """Get a scalar config value with env-var override and strict typing.

        This is used for structured config (e.g. database.*) where defaults are not
        applied, but env-var overrides still need correct type coercion.

        Args:
            key: Dotted config key.
            expected_type: Expected scalar type.

        Returns:
            The configured value, or None if the key is absent in both YAML and env.

        Raises:
            ValueError: If env override cannot be coerced or YAML value type is invalid.
        """

        env_key = _env_var_name(key)
        env_value = os.getenv(env_key)
        if env_value is not None:
            coerced = _coerce_env_value(
                key=key,
                env_key=env_key,
                raw=env_value,
                expected_type=expected_type,
            )
            return cast("T", coerced)

        value = self._get_from_config(key)
        if value is _MISSING:
            return None
        if not isinstance(value, expected_type):
            msg = f"Invalid config type for {key!r} (expected {expected_type.__name__})"
            raise ValueError(msg)  # noqa: TRY004
        return value

    @overload
    def get(self, key: str) -> object | None: ...

    @overload
    def get(self, key: str, default: T) -> T: ...

    def get(self, key: str, default: T | None = None) -> object | None | T:
        """Get configuration value by key with environment-variable overrides.

        Environment override rule:
            - Any dotted key path is overridden by an environment variable named
              `key.upper().replace(".", "_")`.
            - Examples: `database.url` -> `DATABASE_URL`

        Args:
            key: Config key (dot notation, e.g. "external_sources.fake.enabled").
            default: Default value if key is not found.

        Returns:
            Configuration value, possibly overridden by an environment variable.

        Raises:
            ValueError: If env override is present but cannot be coerced to expected type.
        """

        env_key = _env_var_name(key)
        env_value = os.getenv(env_key)
        if env_value is not None:
            expected_type = self._get_expected_scalar_type(key=key, default=default)
            coerced = _coerce_env_value(
                key=key, env_key=env_key, raw=env_value, expected_type=expected_type
            )
            return cast("T", coerced) if default is not None else coerced

        value = self._get_from_config(key)
        if value is _MISSING:
            return default
        return value

    def get_document_storage_path(self) -> Path:
        """Get the path for document storage.

        Returns:
            Path to document storage directory.
        """
        storage_path = self.get("document_storage_path", "data/documents")
        return Path(storage_path).expanduser().resolve()

    def get_external_source_config(self, provider: str) -> dict[str, object]:
        """Get configuration for a specific external source provider.

        Args:
            provider: Provider identifier.

        Returns:
            Configuration dictionary for the provider.
        """
        config_key = f"external_sources.{provider}"
        result: object = self.get(config_key, {})
        if not isinstance(result, dict):
            return {}
        return result

    def get_database_config(self) -> DatabaseConfig:
        """Get the effective database configuration with env-var overrides applied.

        Returns a `DatabaseConfig` that reflects environment-variable overrides per module
        convention:

            - `database.url` -> `DATABASE_URL`
            - `database.host` -> `DATABASE_HOST`
            - etc.

        Returns:
            A `DatabaseConfig` mapping, either as a full URL or as connection components.

        Raises:
            ValueError: If neither YAML `database` nor any `DATABASE_*` env vars are set.
            ValueError: If database config is missing required keys or has invalid types.
        """

        database_section = self._get_from_config("database")
        env_config_present = any(
            os.getenv(key) is not None
            for key in (
                "DATABASE_URL",
                "DATABASE_HOST",
                "DATABASE_PORT",
                "DATABASE_USER",
                "DATABASE_PASSWORD",
                "DATABASE_NAME",
            )
        )
        if database_section is _MISSING and not env_config_present:
            msg = "Database configuration not found in config file"
            raise ValueError(msg)

        url = self._get_typed_value(key="database.url", expected_type=str)
        if url:
            return {"url": url}

        host = self._get_typed_value(key="database.host", expected_type=str)
        port = self._get_typed_value(key="database.port", expected_type=int)
        user = self._get_typed_value(key="database.user", expected_type=str)
        password = self._get_typed_value(key="database.password", expected_type=str)
        name = self._get_typed_value(key="database.name", expected_type=str)

        missing_keys: list[str] = []
        if host is None:
            missing_keys.append("host")
        if port is None:
            missing_keys.append("port")
        if user is None:
            missing_keys.append("user")
        if password is None:
            missing_keys.append("password")
        if name is None:
            missing_keys.append("name")

        if missing_keys:
            msg = (
                f"Database configuration missing required keys: {', '.join(missing_keys)}"
            )
            raise ValueError(msg)

        # Help mypy understand non-None after validation.
        assert host is not None
        assert port is not None
        assert user is not None
        assert password is not None
        assert name is not None

        return {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "name": name,
        }
