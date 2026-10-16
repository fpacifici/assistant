"""Renders a note's blocks back into one markdown document."""

from __future__ import annotations

from typing import TYPE_CHECKING

from assistant.models.schema import MarkdownBlockType, NodeType
from assistant.search.analysis import markdown_to_plain

if TYPE_CHECKING:
    from collections.abc import Iterable

    from assistant.models.schema import Node


def node_markdown(node: Node) -> str:
    """The markdown of one block.

    Markdown blocks are stored as markdown already and legacy text nodes are
    plain text. Attachment payloads are a markdown link to the file: only
    the link text (the file name) is kept, the URL means nothing to a model.
    """
    payload = (node.payload or "").strip()
    if node.node_type == NodeType.ATTACHMENT:
        return markdown_to_plain(payload)
    return payload


def note_markdown(nodes: Iterable[Node]) -> str:
    """Join a note's blocks, in order, into one markdown document.

    Blocks are separated by a blank line, except consecutive list items,
    which stay on adjacent lines so they read as one list. Empty blocks are
    skipped.

    Args:
        nodes: The note's nodes, ordered by position.

    Returns:
        The note body as markdown (empty for a note without content).
    """
    parts: list[str] = []
    previous_is_list_item = False
    for node in nodes:
        text = node_markdown(node)
        if not text:
            continue
        is_list_item = node.block_type == MarkdownBlockType.LIST_ITEM
        if parts:
            parts.append("\n" if is_list_item and previous_is_list_item else "\n\n")
        parts.append(text)
        previous_is_list_item = is_list_item
    return "".join(parts)
