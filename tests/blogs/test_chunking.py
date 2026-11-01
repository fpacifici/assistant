"""Tests for splitting a post into embeddable chunks."""

from __future__ import annotations

from datetime import UTC, datetime

from assistant.blogs.chunking import PostInfo, chunk_post
from assistant.vectors.chunking import CHUNK_SIZE

_PUBLISHED = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def _post(summary: str | None = "A short summary.") -> PostInfo:
    return PostInfo(
        title="On databases",
        source_title="Example Blog",
        summary=summary,
        url="https://blog.example.com/db",
        published_at=_PUBLISHED,
    )


def test_every_chunk_starts_with_title_source_and_summary() -> None:
    chunks = chunk_post(_post(), "Indexes are great.")
    assert len(chunks) == 1
    assert chunks[0].text == (
        "Title: On databases\nSource: Example Blog\nSummary: A short summary."
        "\n\nIndexes are great."
    )


def test_a_post_with_no_text_is_one_header_chunk() -> None:
    chunks = chunk_post(_post(), "")
    assert [chunk.text for chunk in chunks] == [
        "Title: On databases\nSource: Example Blog\nSummary: A short summary."
    ]


def test_no_summary_leaves_the_line_out() -> None:
    chunks = chunk_post(_post(summary=None), "")
    assert chunks[0].text == "Title: On databases\nSource: Example Blog"


def test_sections_and_sizes_follow_the_note_rules() -> None:
    text = "Intro.\n\n# First\n\nOne.\n\n## Deep\n\n" + "word " * (CHUNK_SIZE // 2)
    chunks = chunk_post(_post(), text)
    sections = [chunk.metadata.get("section") for chunk in chunks]
    assert sections[:3] == [None, "First", "First > Deep"]
    assert len(chunks) > 3
    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))
    assert "Section: First > Deep" in chunks[2].text


def test_metadata() -> None:
    [chunk] = chunk_post(_post(), "Text.")
    assert chunk.metadata == {
        "title": "On databases",
        "source_title": "Example Blog",
        "url": "https://blog.example.com/db",
        "published_at": _PUBLISHED.isoformat(),
        "chunk_index": 0,
    }
