"""Configuration management for the assistant package."""

import os
from pathlib import Path
from typing import Any

import yaml


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
            project_root = Path(__file__).parent.parent.parent.parent
            config_path = project_root / "config.yaml"
        else:
            config_path = Path(config_path)

        self.config_path = config_path
        self._config: dict[str, Any] = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from YAML file."""
        if not self.config_path.exists():
            self._config = {}
            return

        with self.config_path.open() as f:
            self._config = yaml.safe_load(f) or {}

    def get(self, key: str, default: Any = None) -> Any:  # noqa: ANN401
        """Get configuration value by key.

        Args:
            key: Configuration key (supports dot notation, e.g., "external_sources.fake").
            default: Default value if key is not found.

        Returns:
            Configuration value or default.
        """
        keys = key.split(".")
        value = self._config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                # Check for environment variable override
                env_key = key.upper().replace(".", "_")
                env_value = os.getenv(env_key)
                if env_value is not None:
                    return env_value
                return default

        return value

    def get_document_storage_path(self) -> Path:
        """Get the path for document storage.

        Returns:
            Path to document storage directory.
        """
        storage_path = self.get("document_storage_path", "data/documents")
        # Support environment variable override
        env_path = os.getenv("DOCUMENT_STORAGE_PATH")
        if env_path:
            storage_path = env_path

        return Path(storage_path).expanduser().resolve()

    def get_external_source_config(self, provider: str) -> dict[str, Any]:
        """Get configuration for a specific external source provider.

        Args:
            provider: Provider identifier.

        Returns:
            Configuration dictionary for the provider.
        """
        config_key = f"external_sources.{provider}"
        result = self.get(config_key, {})
        if not isinstance(result, dict):
            return {}
        return result

    def get_database_url(self) -> str:
        """Get database connection URL from configuration.

        Checks environment variable DATABASE_URL first, then falls back to
        database configuration section in YAML file.

        Returns:
            Database connection URL string.

        Raises:
            ValueError: If required configuration is missing.
        """
        # Check for environment variable override first
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            return database_url

        # Get from config file
        db_config = self.get("database", {})
        if not db_config:
            msg = "Database configuration not found in config file"
            raise ValueError(msg)

        host = db_config.get("host", "localhost")
        port = db_config.get("port", 5432)
        user = db_config.get("user", "assistant")
        password = db_config.get("password", "assistant")
        name = db_config.get("name", "assistant")

        return f"postgresql://{user}:{password}@{host}:{port}/{name}"
