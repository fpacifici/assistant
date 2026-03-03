"""Tests for export module."""

from __future__ import annotations

import tarfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from assistant.config import Config
from assistant.export import (
    DB_DUMP_FILENAME,
    LOGICAL_DATA_FILENAME,
    _build_pg_dump_config,
    run_export,
)


def test_build_pg_dump_config_with_components(test_config: Config) -> None:
    """Ensure pg_dump configuration is derived from component database config."""

    cfg = _build_pg_dump_config(test_config)
    assert cfg.user == "test"
    assert cfg.database == "test"
    assert cfg.container_name == "assistant-postgres"


def test_run_export_creates_archive_with_expected_members(
    tmp_path: Path,
    test_config: Config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_export should produce an archive containing dump, data, and documents."""

    # Prepare document storage with a sample file.
    storage_path = test_config.get_document_storage_path()
    storage_path.mkdir(parents=True, exist_ok=True)
    (storage_path / "example.txt").write_text("example", encoding="utf-8")

    # Fake pg_dump runner that writes a small marker file.
    def fake_pg_dump(path: Path) -> None:
        path.write_bytes(b"dummy-dump")

    # Avoid hitting a real database by stubbing out the engine-dependent logic.
    def fake_write_logical_dump(engine: object, output_path: Path) -> None:  # noqa: ARG001
        output_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr("assistant.export._write_logical_dump", fake_write_logical_dump)
    monkeypatch.setattr("assistant.export.get_engine", lambda: MagicMock())

    output_archive = tmp_path / "backup.tar.gz"

    run_export(test_config, output_archive, pg_dump_runner=fake_pg_dump)

    assert output_archive.exists()

    with tarfile.open(output_archive, "r:gz") as tar:
        names = tar.getnames()
        assert DB_DUMP_FILENAME in names
        assert LOGICAL_DATA_FILENAME in names
        # The documents directory should be present with at least one entry.
        assert any(name.startswith("documents") for name in names)

