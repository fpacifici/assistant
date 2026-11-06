"""The full text of blog posts, one UTF-8 file per post.

Files live at `<document_storage_path>/blog_posts/<post_id>.txt`, never in the
database (see docs/adr/0004-blog-post-text-in-documents.md). `sweep` is the
only code that removes them, so every way a post can disappear is covered by
one path.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from assistant.config import Config

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from pathlib import Path

SUBDIRECTORY = "blog_posts"
_SWEEP_BATCH = 500


class TextStore:
    """Reads and writes post text under a documents directory."""

    def __init__(self, document_root: Path) -> None:
        """Create a store.

        Args:
            document_root: The documents directory.
        """
        self.root = document_root / SUBDIRECTORY

    def path(self, post_id: uuid.UUID) -> Path:
        """Where a post's text is stored."""
        return self.root / f"{post_id}.txt"

    def write(self, post_id: uuid.UUID, text: str) -> None:
        """Save a post's text, replacing it atomically."""
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.path(post_id)
        partial = path.with_suffix(".partial")
        partial.write_text(text, encoding="utf-8")
        partial.replace(path)

    def read(self, post_id: uuid.UUID) -> str | None:
        """Return a post's text, or `None` if it has no file."""
        try:
            return self.path(post_id).read_text(encoding="utf-8")
        except FileNotFoundError:
            return None

    def sweep(self, existing: Callable[[Iterable[uuid.UUID]], set[uuid.UUID]]) -> int:
        """Delete every file whose post no longer exists.

        Args:
            existing: Given post ids, returns those that still exist.

        Returns:
            The number of files deleted.
        """
        if not self.root.is_dir():
            return 0
        files: dict[uuid.UUID, Path] = {}
        for path in self.root.iterdir():
            try:
                files[uuid.UUID(path.stem)] = path
            except ValueError:
                continue
        ids = list(files)
        removed = 0
        for start in range(0, len(ids), _SWEEP_BATCH):
            batch = ids[start : start + _SWEEP_BATCH]
            alive = existing(batch)
            for post_id in batch:
                if post_id not in alive:
                    files[post_id].unlink(missing_ok=True)
                    self.path(post_id).with_suffix(".partial").unlink(missing_ok=True)
                    removed += 1
        return removed


def create_text_store(config: Config | None = None) -> TextStore:
    """Build the store from config."""
    return TextStore((config or Config()).get_document_storage_path())
