"""Tests for restore module."""

from __future__ import annotations

import json
import tarfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from assistant.config import Config
from assistant.export import DOCUMENTS_DIRNAME, LOGICAL_DATA_FILENAME
from assistant.restore import run_restore


def _create_sample_archive(root: Path) -> Path:
    """Create a minimal archive compatible with the restore logic."""

    data: dict[str, list[object]] = {
        "external_sources": [],
        "documents": [],
        "collections": [],
        "embeddings": [],
    }
    data_path = root / LOGICAL_DATA_FILENAME
    data_path.write_text(json.dumps(data), encoding="utf-8")

    documents_dir = root / DOCUMENTS_DIRNAME
    documents_dir.mkdir(parents=True, exist_ok=True)
    (documents_dir / "note.txt").write_text("content", encoding="utf-8")

    archive_path = root / "backup.tar.gz"
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(data_path, arcname=LOGICAL_DATA_FILENAME)
        tar.add(documents_dir, arcname=DOCUMENTS_DIRNAME)

    return archive_path


def test_run_restore_uses_helpers_and_restores_documents(
    tmp_path: Path,
    test_config: Config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_restore should orchestrate helpers and restore the documents tree."""

    archive_path = _create_sample_archive(tmp_path)

    # Prepare a fake engine with a simple dialect name.
    engine = MagicMock()
    engine.dialect = SimpleNamespace(name="sqlite")

    drop_calls: list[object] = []
    init_calls: list[object] = []
    reset_vector_calls: list[object] = []
    clear_calls: list[object] = []
    restore_app_calls: list[object] = []
    restore_vector_calls: list[object] = []

    monkeypatch.setattr("assistant.restore.get_engine", lambda: engine)

    def fake_drop_database(e: object) -> None:
        drop_calls.append(e)

    def fake_init_database(e: object) -> None:
        init_calls.append(e)

    def fake_reset_vector_tables(e: object) -> None:
        reset_vector_calls.append(e)

    def fake_clear_application_data(session: object) -> None:  # noqa: ARG001
        clear_calls.append(object())

    def fake_restore_application_data(session: object, data: object) -> None:  # noqa: ARG001
        restore_app_calls.append(object())

    def fake_restore_vector_data(e: object, data: object) -> None:  # noqa: ARG001
        restore_vector_calls.append(e)

    monkeypatch.setattr("assistant.restore.drop_database", fake_drop_database)
    monkeypatch.setattr("assistant.restore.init_database", fake_init_database)
    monkeypatch.setattr("assistant.restore._reset_vector_tables", fake_reset_vector_tables)
    monkeypatch.setattr("assistant.restore._clear_application_data", fake_clear_application_data)
    monkeypatch.setattr(
        "assistant.restore._restore_application_data",
        fake_restore_application_data,
    )
    monkeypatch.setattr("assistant.restore._restore_vector_data", fake_restore_vector_data)

    # Ensure the target document directory exists and has a different file so
    # that we can verify it gets replaced.
    target_docs = test_config.get_document_storage_path()
    target_docs.mkdir(parents=True, exist_ok=True)
    (target_docs / "old.txt").write_text("old", encoding="utf-8")

    run_restore(test_config, archive_path)

    assert drop_calls == [engine]
    assert init_calls == [engine]
    assert reset_vector_calls == [engine]
    assert clear_calls
    assert restore_app_calls
    assert restore_vector_calls == [engine]

    # The target documents directory should now contain the content from the archive.
    restored_files = sorted(p.name for p in target_docs.iterdir())
    assert restored_files == ["note.txt"]

