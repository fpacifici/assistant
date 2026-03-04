from __future__ import annotations

"""Database and content restore utilities.

This module implements the core logic to restore database contents and
documents from an archive produced by :mod:`assistant.export`.

The restore procedure uses ``pg_restore`` run inside the ``assistant-postgres``
Docker container to restore the database from the ``db.dump`` file in the
archive, then copies the document storage directory from the archive into the
configured location.
"""

import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

from assistant.config import Config
from assistant.export import DB_DUMP_FILENAME, DOCUMENTS_DIRNAME, _build_pg_dump_config


def _default_pg_restore(dump_path: Path, *, config: Config) -> None:
    """Run pg_restore inside the default Docker container.

    Copies the dump file into the container, then runs pg_restore with
    ``--clean --if-exists`` so that existing objects are dropped before
    restore.

    Args:
        dump_path: Path to the ``db.dump`` file on the host.
        config: Application configuration instance used to discover database
            credentials and container name.

    Raises:
        subprocess.CalledProcessError: If docker cp or pg_restore fails.
        ValueError: If the database configuration is incompatible with this
            runner.
    """
    cfg = _build_pg_dump_config(config)
    container_path = "/tmp/db.dump"

    subprocess.run(
        ["docker", "cp", str(dump_path), f"{cfg.container_name}:{container_path}"],
        check=True,
    )

    env_args: list[str] = []
    if cfg.password:
        env_args = ["-e", f"PGPASSWORD={cfg.password}"]

    subprocess.run(
        [
            "docker",
            "exec",
            *env_args,
            cfg.container_name,
            "pg_restore",
            "-U",
            cfg.user,
            "-d",
            cfg.database,
            "--clean",
            "--if-exists",
            "-Fc",
            container_path,
        ],
        check=True,
    )


def _restore_documents_directory(config: Config, extracted_root: Path) -> None:
    """Restore the document storage directory from the extracted archive.

    Args:
        config: Application configuration instance.
        extracted_root: Root directory where the archive has been extracted.
    """
    source_dir = extracted_root / DOCUMENTS_DIRNAME
    target_dir = config.get_document_storage_path()

    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    if source_dir.exists():
        shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)


def run_restore(config: Config, archive_path: Path) -> None:
    """Restore database and document contents from a backup archive.

    The archive must have been produced by :func:`assistant.export.run_export`.
    It must contain ``db.dump`` (pg_dump custom format) and ``documents/``.
    Database restore is performed by running pg_restore inside the
    ``assistant-postgres`` Docker container.

    Args:
        config: Application configuration instance.
        archive_path: Path to the ``.tar.gz`` archive to restore from.

    Raises:
        FileNotFoundError: If the archive or required members are missing.
        subprocess.CalledProcessError: If pg_restore fails.
    """
    archive_path = archive_path.resolve()
    if not archive_path.exists():
        msg = f"Archive file does not exist: {archive_path}"
        raise FileNotFoundError(msg)

    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)

        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(path=tmp_dir)

        db_dump_path = tmp_dir / DB_DUMP_FILENAME
        if not db_dump_path.exists():
            msg = f"Database dump not found in archive: {DB_DUMP_FILENAME}"
            raise FileNotFoundError(msg)

        _default_pg_restore(db_dump_path, config=config)
        _restore_documents_directory(config, tmp_dir)
