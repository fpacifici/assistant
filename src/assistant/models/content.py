from __future__ import annotations

"""Shared in-memory representation of document content.

The :class:`DocumentContent` dataclass is used by both adapters and agents to
pass raw document bytes plus lightweight metadata around without depending on
any particular storage backend or vector store implementation.
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass
class DocumentContent:
    """Document content and associated metadata.

    Attributes:
        uuid: UUID of the document (typically used as filename when stored).
        bytes: Raw bytes of the document body.
        title: Optional human-readable title for the document.
        metadata: Arbitrary key-value metadata describing the document.
    """

    uuid: uuid.UUID
    bytes: bytes
    title: str = ""
    metadata: Mapping[str, str] = field(default_factory=dict)
