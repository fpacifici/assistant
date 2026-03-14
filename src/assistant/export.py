from __future__ import annotations

"""Database and content export utilities.

This module implements the core logic to create a backup archive that contains:

* A ``pg_dump`` of the database (custom format), produced by running pg_dump
  inside the ``assistant-postgres`` Docker container.
* A copy of the document storage directory.

The main entry point is :func:`run_export`, which is intended to be invoked by
CLI scripts and other orchestration layers.
"""

import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from assistant.config import Config, DatabaseComponentsConfig, DatabaseConfig

DB_DUMP_FILENAME = "db.dump"
DOCUMENTS_DIRNAME = "documents"


@dataclass(frozen=True)
class _PgDumpConfig:
    """Internal configuration required to run pg_dump inside Docker."""

    user: str
    password: str | None
    database: str
    container_name: str


def _build_pg_dump_config(
    config: Config, *, container_name: str = "assistant-postgres"
) -> _PgDumpConfig:
    """Create pg_dump configuration from the application Config.

    Args:
        config: Application configuration instance.
        container_name: Name of the PostgreSQL container used for docker exec.

    Returns:
        Parsed configuration for invoking pg_dump.

    Raises:
        ValueError: If the database configuration does not provide the required
            fields to construct pg_dump arguments.
    """

    db_config: DatabaseConfig = config.get_database_config()
    url = db_config.get("url")
    if isinstance(url, str) and url:
        msg = (
            "Database config must use component fields (host/port/user/password/name) "
            "for container-based pg_dump. URL-only configuration cannot be used "
            "for automated pg_dump invocation."
        )
        raise ValueError(msg)

    components = cast("DatabaseComponentsConfig", db_config)
    return _PgDumpConfig(
        user=components["user"],
        password=components.get("password"),
        database=components["name"],
        container_name=container_name,
    )


def _default_pg_dump_runner(dump_path: Path, *, config: Config) -> None:
    """Run pg_dump inside the default Docker container.

    This uses ``docker exec`` to invoke pg_dump in the container named
    ``assistant-postgres`` (or the container name configured in Docker
    Compose). The dump is written to ``dump_path`` in custom format.

    Args:
        dump_path: Target path for the pg_dump output.
        config: Application configuration instance used to discover database
            credentials.

    Raises:
        subprocess.CalledProcessError: If the pg_dump command fails.
        ValueError: If the database configuration is incompatible with this
            runner.
    """

    dump_cfg = _build_pg_dump_config(config)
    env_args: list[str] = []
    if dump_cfg.password:
        env_args = ["-e", f"PGPASSWORD={dump_cfg.password}"]

    cmd: list[str] = [
        "docker",
        "exec",
        *env_args,
        dump_cfg.container_name,
        "pg_dump",
        "-U",
        dump_cfg.user,
        "-d",
        dump_cfg.database,
        "-Fc",
    ]

    dump_path.parent.mkdir(parents=True, exist_ok=True)
    with dump_path.open("wb") as dump_file:
        subprocess.run(cmd, check=True, stdout=dump_file)


def run_export(config: Config, output_path: Path) -> None:
    """Create a backup archive containing database and document contents.

    The produced ``tar.gz`` archive has the following layout:

    - ``db.dump``: Raw output from ``pg_dump`` (custom format), created by
      running pg_dump inside the ``assistant-postgres`` Docker container.
    - ``documents/``: Copy of the configured document storage directory.

    Args:
        config: Application configuration instance.
        output_path: Target path for the resulting ``.tar.gz`` archive.

    Raises:
        subprocess.CalledProcessError: If the pg_dump command fails.
        ValueError: If the database configuration is incompatible with the
            Docker-based pg_dump runner.
    """

    output_path = output_path.resolve()

    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)

        db_dump_path = tmp_dir / DB_DUMP_FILENAME
        documents_tmp_dir = tmp_dir / DOCUMENTS_DIRNAME

        # 1. Run pg_dump inside the Docker container.
        _default_pg_dump_runner(db_dump_path, config=config)

        # 2. Copy document storage directory.
        storage_path = config.get_document_storage_path()
        if storage_path.exists():
            shutil.copytree(storage_path, documents_tmp_dir, dirs_exist_ok=True)
        else:
            documents_tmp_dir.mkdir(parents=True, exist_ok=True)

        # 3. Create the final tar.gz archive with stable, predictable names.
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(output_path, "w:gz") as tar:
            tar.add(db_dump_path, arcname=DB_DUMP_FILENAME)
            tar.add(documents_tmp_dir, arcname=DOCUMENTS_DIRNAME)
