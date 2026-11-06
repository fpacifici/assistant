"""Splits a useful post into the chunks that get embedded.

Sections and sizes are the same as for notes (`assistant.vectors.chunking`).
Every chunk starts with the post's title, source and summary, so it is
meaningful on its own. A post with no stored text yields one chunk, the header.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from assistant.vectors.chunking import split_markdown

if TYPE_CHECKING:
    from datetime import datetime


@dataclass(frozen=True, slots=True)
class PostInfo:
    """What a chunk needs to know about its post."""

    title: str
    source_title: str
    summary: str | None
    url: str
    published_at: datetime


@dataclass(frozen=True, slots=True)
class PostChunk:
    """One embeddable piece of a post.

    Attributes:
        index: Position of the chunk in the post, from 0.
        text: The text that is embedded and stored: header plus content.
        metadata: JSON-serializable metadata stored with the chunk.
    """

    index: int
    text: str
    metadata: dict[str, str | int]


def _header(post: PostInfo, section: str) -> str:
    lines = [f"Title: {post.title}", f"Source: {post.source_title}"]
    if post.summary:
        lines.append(f"Summary: {post.summary}")
    if section:
        lines.append(f"Section: {section}")
    return "\n".join(lines)


def chunk_post(post: PostInfo, text: str) -> list[PostChunk]:
    """Split a post into chunks ready to embed.

    Args:
        post: The post.
        text: Its stored text, or "" if it has none.

    Returns:
        The chunks, in post order; always at least one.
    """
    chunks: list[PostChunk] = []
    for index, (section, piece) in enumerate(split_markdown(text) or [("", "")]):
        header = _header(post, section)
        metadata: dict[str, str | int] = {
            "title": post.title,
            "source_title": post.source_title,
            "url": post.url,
            "published_at": post.published_at.isoformat(),
            "chunk_index": index,
        }
        if section:
            metadata["section"] = section
        body = f"{header}\n\n{piece}" if piece else header
        chunks.append(PostChunk(index=index, text=body, metadata=metadata))
    return chunks
