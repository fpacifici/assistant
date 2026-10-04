"""Adapters module for external source integration."""

from assistant.adapters.content import (
    DocumentContent,
    read_content,
    write_content,
)
from assistant.adapters.dataload import load_data
from assistant.adapters.import_source import ImportSource
from assistant.adapters.notes_import import ImportReport, run_import
from assistant.adapters.registry import Registry
from assistant.adapters.source import ExternalSource

__all__ = [
    "DocumentContent",
    "ExternalSource",
    "ImportReport",
    "ImportSource",
    "Registry",
    "load_data",
    "read_content",
    "run_import",
    "write_content",
]
