"""Notes-import source interface definition.

A sibling to `ExternalSource` (`adapters/source.py`), for one-shot bulk
imports of external content directly into the notes system rather than
incremental RAG sync. Deliberately narrower than `ExternalSource`: no `since`
cursor (a directory import is not incremental), and no
`build()`/`ExternalSourceInstanceConfig`/`Registry` machinery — there is
exactly one implementation this iteration, constructed directly by its CLI.
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

    Mirrors ExternalSource's list-then-fetch shape, but for bulk import into
    the notes system rather than incremental RAG document sync.
    """

    @abstractmethod
    def list_documents(self) -> list[str]:
        """Return identifiers for every document available to import."""
        ...

    @abstractmethod
    def get_note(self, document_id: str) -> ImportedNote:
        """Fetch and parse one document into a notebook name + storable blocks."""
        ...
