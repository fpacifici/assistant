"""Notes-import source interface definition.

For one-shot bulk imports of external content directly into the notes
system. There is no `since` cursor (a directory import is not incremental)
and no registry: the single implementation (`HTMLFileImportSource`) is
constructed directly by its callers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from assistant.adapters.html_parser import ParsedNote


@dataclass(frozen=True, slots=True)
class ImportedNote:
    """A single note ready for persistence, as returned by an ImportSource."""

    notebook_name: str
    parsed: ParsedNote


class ImportSource(ABC):
    """Abstract base class for one-shot notes-import sources.

    List the documents, then fetch and parse each one for import into the
    notes system.
    """

    @abstractmethod
    def list_documents(self) -> list[str]:
        """Return identifiers for every document available to import."""
        ...

    @abstractmethod
    def get_note(self, document_id: str) -> ImportedNote:
        """Fetch and parse one document into a notebook name + storable blocks."""
        ...
