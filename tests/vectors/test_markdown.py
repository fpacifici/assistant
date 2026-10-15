"""Tests for rendering a note's blocks into markdown."""

from __future__ import annotations

import uuid

from assistant.models.schema import MarkdownBlockType, Node, NodeType
from assistant.vectors.markdown import node_markdown, note_markdown


def _markdown(payload: str, block_type: MarkdownBlockType) -> Node:
    return Node(
        node_type=NodeType.MARKDOWN.value,
        payload=payload,
        block_type=block_type.value,
    )


def _attachment(payload: str) -> Node:
    return Node(
        node_type=NodeType.ATTACHMENT.value,
        payload=payload,
        attachment_id=uuid.uuid4(),
    )


# --- Single blocks ---


def test_markdown_block_keeps_its_markdown() -> None:
    node = _markdown("## Trip **plan**", MarkdownBlockType.HEADING)

    assert node_markdown(node) == "## Trip **plan**"


def test_text_node_is_kept_as_is() -> None:
    node = Node(node_type=NodeType.TEXT.value, payload="plain text")

    assert node_markdown(node) == "plain text"


def test_attachment_becomes_its_link_text() -> None:
    node = _attachment("[boarding-pass.pdf](/files/123/content)")

    assert node_markdown(node) == "boarding-pass.pdf"


# --- Whole note ---


def test_blocks_are_separated_by_blank_lines() -> None:
    nodes = [
        _markdown("# Rome", MarkdownBlockType.HEADING),
        _markdown("We saw the Colosseum.", MarkdownBlockType.PARAGRAPH),
    ]

    assert note_markdown(nodes) == "# Rome\n\nWe saw the Colosseum."


def test_consecutive_list_items_stay_one_list() -> None:
    nodes = [
        _markdown("Packing:", MarkdownBlockType.PARAGRAPH),
        _markdown("- passport", MarkdownBlockType.LIST_ITEM),
        _markdown("- charger", MarkdownBlockType.LIST_ITEM),
        _markdown("Done.", MarkdownBlockType.PARAGRAPH),
    ]

    assert note_markdown(nodes) == "Packing:\n\n- passport\n- charger\n\nDone."


def test_empty_blocks_are_skipped() -> None:
    nodes = [
        _markdown("First", MarkdownBlockType.PARAGRAPH),
        _markdown("   ", MarkdownBlockType.PARAGRAPH),
        _markdown("Second", MarkdownBlockType.PARAGRAPH),
    ]

    assert note_markdown(nodes) == "First\n\nSecond"


def test_note_without_blocks_is_empty() -> None:
    assert note_markdown([]) == ""
