"""Tests for the post text files."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from pathlib import Path

from assistant.blogs.text_store import TextStore, create_text_store
from assistant.config import Config


def _alive(*ids: uuid.UUID):  # noqa: ANN202
    def existing(batch: Iterable[uuid.UUID]) -> set[uuid.UUID]:
        return set(batch) & set(ids)

    return existing


def test_round_trip_keeps_unicode(tmp_path: Path) -> None:
    store = TextStore(tmp_path)
    post_id = uuid.uuid4()
    store.write(post_id, "caffè ☕")
    assert store.read(post_id) == "caffè ☕"
    assert store.path(post_id) == tmp_path / "blog_posts" / f"{post_id}.txt"


def test_a_post_without_a_file_reads_none(tmp_path: Path) -> None:
    assert TextStore(tmp_path).read(uuid.uuid4()) is None


def test_write_replaces(tmp_path: Path) -> None:
    store = TextStore(tmp_path)
    post_id = uuid.uuid4()
    store.write(post_id, "old")
    store.write(post_id, "new")
    assert store.read(post_id) == "new"
    assert [path.name for path in store.root.iterdir()] == [f"{post_id}.txt"]


def test_sweep_only_removes_orphans(tmp_path: Path) -> None:
    store = TextStore(tmp_path)
    kept, orphan = uuid.uuid4(), uuid.uuid4()
    store.write(kept, "kept")
    store.write(orphan, "orphan")
    assert store.sweep(_alive(kept)) == 1
    assert store.read(kept) == "kept"
    assert store.read(orphan) is None


def test_sweep_leaves_other_files_alone(tmp_path: Path) -> None:
    store = TextStore(tmp_path)
    store.write(uuid.uuid4(), "orphan")
    stranger = store.root / "notes.txt"
    stranger.write_text("not ours")
    sibling = tmp_path / f"{uuid.uuid4()}.txt"
    sibling.write_text("an older document")
    assert store.sweep(_alive()) == 1
    assert stranger.exists()
    assert sibling.exists()


def test_sweep_removes_a_partial_write(tmp_path: Path) -> None:
    store = TextStore(tmp_path)
    store.root.mkdir(parents=True)
    partial = store.root / f"{uuid.uuid4()}.partial"
    partial.write_text("half")
    assert store.sweep(_alive()) == 1
    assert not partial.exists()


def test_sweep_with_no_directory_yet(tmp_path: Path) -> None:
    assert TextStore(tmp_path).sweep(_alive()) == 0


def test_store_uses_the_documents_directory(test_config: Config) -> None:
    store = create_text_store(test_config)
    assert store.root == test_config.get_document_storage_path() / "blog_posts"
