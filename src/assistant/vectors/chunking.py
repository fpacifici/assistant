"""Splits a note into the chunks that get embedded.

The note markdown is split by headings first (so a chunk does not straddle
two sections), then each section into chunks of at most `CHUNK_SIZE`
characters overlapping by `CHUNK_OVERLAP`. Every chunk's text starts with a
short header naming the note, its notebook and the section, so a chunk is
meaningful on its own both to the embedding model and to the agent reading
it back.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

if TYPE_CHECKING:
    import uuid
    from datetime import datetime

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

_HEADERS = [("#", "h1"), ("##", "h2"), ("###", "h3")]


@dataclass(frozen=True, slots=True)
class NoteInfo:
    """What a chunk needs to know about its note."""

    note_id: uuid.UUID
    notebook_id: uuid.UUID
    notebook_name: str
    title: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class NoteChunk:
    """One embeddable piece of a note.

    Attributes:
        index: Position of the chunk in the note, from 0.
        text: The text that is embedded and stored: header plus content.
        metadata: JSON-serializable metadata stored with the chunk.
    """

    index: int
    text: str
    metadata: dict[str, str | int]


def _header(note: NoteInfo, section: str) -> str:
    lines = [f"Title: {note.title}", f"Notebook: {note.notebook_name}"]
    if section:
        lines.append(f"Section: {section}")
    return "\n".join(lines)


def _sections(markdown: str) -> list[tuple[str, str]]:
    """(section path, content) pairs, e.g. ("Trip > Food", "## Food ...")."""
    splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=_HEADERS, strip_headers=False
    )
    sections: list[tuple[str, str]] = []
    for doc in splitter.split_text(markdown):
        path = " > ".join(
            str(doc.metadata[key]) for _, key in _HEADERS if key in doc.metadata
        )
        sections.append((path, doc.page_content))
    return sections


def chunk_note(note: NoteInfo, markdown: str, *, index_version: int) -> list[NoteChunk]:
    """Split a note into chunks ready to embed.

    A note without content still yields one chunk (just the header), so it
    can be found by its title.

    Args:
        note: The note the markdown belongs to.
        markdown: The note body, see `assistant.vectors.markdown.note_markdown`.
        index_version: Recorded in each chunk's metadata.

    Returns:
        The chunks, in note order.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )
    pieces: list[tuple[str, str]] = [
        (section, piece)
        for section, content in _sections(markdown)
        for piece in splitter.split_text(content)
    ]
    if not pieces:
        pieces = [("", "")]

    chunks: list[NoteChunk] = []
    for index, (section, piece) in enumerate(pieces):
        header = _header(note, section)
        metadata: dict[str, str | int] = {
            "title": note.title,
            "notebook_name": note.notebook_name,
            "created_at": note.created_at.isoformat(),
            "updated_at": note.updated_at.isoformat(),
            "chunk_index": index,
            "index_version": index_version,
        }
        if section:
            metadata["section"] = section
        text = f"{header}\n\n{piece}" if piece else header
        chunks.append(NoteChunk(index=index, text=text, metadata=metadata))
    return chunks
