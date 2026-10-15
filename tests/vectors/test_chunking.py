"""Tests for splitting a note into embeddable chunks."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from assistant.vectors.chunking import CHUNK_SIZE, NoteInfo, chunk_note

_CREATED = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
_UPDATED = datetime(2026, 2, 3, 4, 5, 6, tzinfo=UTC)


def _note(title: str = "Rome trip") -> NoteInfo:
    return NoteInfo(
        note_id=uuid.uuid4(),
        notebook_id=uuid.uuid4(),
        notebook_name="Travel",
        title=title,
        created_at=_CREATED,
        updated_at=_UPDATED,
    )


# --- Header ---


def test_every_chunk_starts_with_title_and_notebook() -> None:
    chunks = chunk_note(_note(), "We saw the Colosseum.", index_version=3)

    assert len(chunks) == 1
    assert chunks[0].text == (
        "Title: Rome trip\nNotebook: Travel\n\nWe saw the Colosseum."
    )


def test_note_without_content_is_one_header_chunk() -> None:
    chunks = chunk_note(_note("Empty"), "", index_version=1)

    assert [chunk.text for chunk in chunks] == ["Title: Empty\nNotebook: Travel"]


# --- Sections ---


def test_headings_split_the_note_and_name_the_section() -> None:
    markdown = (
        "Intro.\n\n# Rome\n\nColosseum.\n\n## Food\n\nCarbonara.\n\n# Florence\n\nDuomo."
    )

    chunks = chunk_note(_note(), markdown, index_version=1)

    sections = [chunk.metadata.get("section") for chunk in chunks]
    assert sections == [None, "Rome", "Rome > Food", "Florence"]
    assert "Section: Rome > Food" in chunks[2].text
    assert "Carbonara." in chunks[2].text
    assert "Duomo." not in chunks[2].text


def test_long_sections_are_split_with_overlap() -> None:
    words = " ".join(f"word{i}" for i in range(600))

    chunks = chunk_note(_note(), words, index_version=1)

    assert len(chunks) > 1
    header = "Title: Rome trip\nNotebook: Travel\n\n"
    bodies = [chunk.text.removeprefix(header) for chunk in chunks]
    assert all(len(body) <= CHUNK_SIZE for body in bodies)
    # Consecutive chunks overlap.
    assert bodies[0].split()[-1] in bodies[1]


# --- Metadata ---


def test_metadata_describes_the_note() -> None:
    chunks = chunk_note(_note(), "# Rome\n\nColosseum.", index_version=7)

    assert chunks[0].metadata == {
        "title": "Rome trip",
        "notebook_name": "Travel",
        "created_at": "2026-01-02T03:04:05+00:00",
        "updated_at": "2026-02-03T04:05:06+00:00",
        "chunk_index": 0,
        "index_version": 7,
        "section": "Rome",
    }


def test_chunks_are_numbered_in_order() -> None:
    chunks = chunk_note(_note(), "# A\n\na\n\n# B\n\nb\n\n# C\n\nc", index_version=1)

    assert [chunk.index for chunk in chunks] == [0, 1, 2]
    assert [chunk.metadata["chunk_index"] for chunk in chunks] == [0, 1, 2]
