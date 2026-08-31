"""HTML-directory ImportSource: one notebook per subdirectory, one note per file."""

from __future__ import annotations

from pathlib import Path

from assistant.adapters.html_parser import parse_html_note
from assistant.adapters.import_source import ImportedNote, ImportSource


class HTMLFileImportSource(ImportSource):
    """Treats a root directory's immediate subdirectories as notebooks.

    Each `.html` file directly inside a subdirectory (one level only — deeper
    nesting is ignored) is one note.
    """

    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir

    def list_documents(self) -> list[str]:
        """Return one identifier per `.html` file directly inside each subdirectory.

        Identifiers are paths relative to root_dir, e.g. "Personal/note1.html",
        which also encode the notebook name.
        """
        return [
            str(html_path.relative_to(self._root_dir))
            for entry in sorted(p for p in self._root_dir.iterdir() if p.is_dir())
            for html_path in sorted(entry.glob("*.html"))
        ]

    def get_note(self, document_id: str) -> ImportedNote:
        """Read and parse the `.html` file at `document_id` into an `ImportedNote`.

        `document_id` is a path relative to root_dir, as returned by
        `list_documents`; its first path segment is used as the notebook name.
        """
        html_path = self._root_dir / document_id
        notebook_name = Path(document_id).parts[0]
        html = html_path.read_text(encoding="utf-8")
        parsed = parse_html_note(html, fallback_title=html_path.stem)
        return ImportedNote(notebook_name=notebook_name, parsed=parsed)
