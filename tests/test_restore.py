"""Tests for restore module."""

from __future__ import annotations

import shutil
import tarfile
from pathlib import Path
import pytest

from assistant.config import Config
from assistant.export import DB_DUMP_FILENAME, DOCUMENTS_DIRNAME
from assistant.restore import run_restore


def _create_sample_archive(root: Path) -> Path:
    """Create a minimal archive compatible with the restore logic (db.dump + documents/)."""

    dump_path = root / DB_DUMP_FILENAME
    dump_path.write_bytes(b"dummy-pg-dump")

    documents_dir = root / DOCUMENTS_DIRNAME
    documents_dir.mkdir(parents=True, exist_ok=True)
    (documents_dir / "note.txt").write_text("content", encoding="utf-8")

    archive_path = root / "backup.tar.gz"
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(dump_path, arcname=DB_DUMP_FILENAME)
        tar.add(documents_dir, arcname=DOCUMENTS_DIRNAME)

    return archive_path


def test_run_restore_calls_pg_restore_and_restores_documents(
    tmp_path: Path,
    test_config: Config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_restore should run pg_restore and restore the documents tree."""

    archive_path = _create_sample_archive(tmp_path)

    restore_calls: list[tuple[Path, Config]] = []
    doc_restore_calls: list[tuple[Config, Path]] = []

    def fake_pg_restore(dump_path: Path, *, config: Config) -> None:
        restore_calls.append((dump_path, config))

    def fake_restore_documents(config: Config, extracted_root: Path) -> None:
        doc_restore_calls.append((config, extracted_root))
        # Actually copy documents so we can assert on the result.
        source_dir = extracted_root / DOCUMENTS_DIRNAME
        target_dir = config.get_document_storage_path()
        if target_dir.exists():
            shutil.rmtree(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        if source_dir.exists():
            shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)

    monkeypatch.setattr("assistant.restore._default_pg_restore", fake_pg_restore)
    monkeypatch.setattr(
        "assistant.restore._restore_documents_directory",
        fake_restore_documents,
    )

    target_docs = test_config.get_document_storage_path()
    target_docs.mkdir(parents=True, exist_ok=True)
    (target_docs / "old.txt").write_text("old", encoding="utf-8")

    run_restore(test_config, archive_path)

    assert len(restore_calls) == 1
    dump_path, config = restore_calls[0]
    assert dump_path.name == DB_DUMP_FILENAME
    assert config is test_config

    assert len(doc_restore_calls) == 1
    _, extracted_root = doc_restore_calls[0]
    # extracted_root was the temp dir used during restore (since deleted)
    assert extracted_root is not None

    restored_files = sorted(p.name for p in target_docs.iterdir())
    assert restored_files == ["note.txt"]


def test_run_restore_raises_when_dump_missing(
    tmp_path: Path,
    test_config: Config,
) -> None:
    """run_restore should raise FileNotFoundError when archive has no db.dump."""

    # Archive with only documents/, no db.dump.
    documents_dir = tmp_path / DOCUMENTS_DIRNAME
    documents_dir.mkdir(parents=True, exist_ok=True)
    archive_path = tmp_path / "incomplete.tar.gz"
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(documents_dir, arcname=DOCUMENTS_DIRNAME)

    with pytest.raises(FileNotFoundError, match=DB_DUMP_FILENAME):
        run_restore(test_config, archive_path)
