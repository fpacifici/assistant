"""Tests for export module."""

from __future__ import annotations

import tarfile
from pathlib import Path

import pytest

from assistant.config import Config
from assistant.export import (
    DB_DUMP_FILENAME,
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
    """run_export should produce an archive containing dump and documents."""

    # Prepare document storage with a sample file.
    storage_path = test_config.get_document_storage_path()
    storage_path.mkdir(parents=True, exist_ok=True)
    (storage_path / "example.txt").write_text("example", encoding="utf-8")

    # Fake pg_dump runner that writes a small marker file (Docker-only export).
    def fake_pg_dump(path: Path, *, config: object) -> None:  # noqa: ARG001
        path.write_bytes(b"dummy-dump")

    monkeypatch.setattr("assistant.export._default_pg_dump_runner", fake_pg_dump)

    output_archive = tmp_path / "backup.tar.gz"

    run_export(test_config, output_archive)

    assert output_archive.exists()

    with tarfile.open(output_archive, "r:gz") as tar:
        names = tar.getnames()
        assert DB_DUMP_FILENAME in names
        # The documents directory should be present with at least one entry.
        assert any(name.startswith("documents") for name in names)
