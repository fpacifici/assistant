"""Tests for the pure HTML->blocks parser used by the notes-import adapter."""

from __future__ import annotations

import pytest

from assistant.adapters.html_parser import ParsedBlock, parse_html_note

# ---------------------------------------------------------------------------
# Title resolution
# ---------------------------------------------------------------------------


def test_title_from_h1() -> None:
    html = "<h1>My Title</h1><p>content</p>"
    parsed = parse_html_note(html, fallback_title="fallback")
    assert parsed.title == "My Title"


def test_title_falls_back_to_meta() -> None:
    html = '<meta itemprop="title" content="Meta Title"><p>content</p>'
    parsed = parse_html_note(html, fallback_title="fallback")
    assert parsed.title == "Meta Title"


def test_title_falls_back_to_filename() -> None:
    html = "<p>content, no h1 or meta title here</p>"
    parsed = parse_html_note(html, fallback_title="fallback-name")
    assert parsed.title == "fallback-name"


def test_first_h1_consumed_as_title_not_duplicated() -> None:
    html = "<h1>Title</h1><h2>Sub</h2>"
    parsed = parse_html_note(html, fallback_title="fallback")
    assert parsed.title == "Title"
    assert parsed.blocks == [ParsedBlock("heading", "## Sub")]


# ---------------------------------------------------------------------------
# web.clip skip
# ---------------------------------------------------------------------------


def test_web_clip_source_is_skipped() -> None:
    html = (
        '<meta itemprop="source" content="web.clip">'
        "<h1>Some clipped page</h1><p>content</p>"
    )
    parsed = parse_html_note(html, fallback_title="fallback")
    assert parsed.skip is True
    assert parsed.title == ""
    assert parsed.blocks == []


def test_non_web_clip_source_not_skipped() -> None:
    html = '<meta itemprop="source" content="desktop"><h1>Title</h1>'
    parsed = parse_html_note(html, fallback_title="fallback")
    assert parsed.skip is False
    assert parsed.title == "Title"


# ---------------------------------------------------------------------------
# Lists
# ---------------------------------------------------------------------------


def test_unordered_list_to_list_items() -> None:
    html = "<ul><li>One</li><li>Two</li></ul>"
    parsed = parse_html_note(html, fallback_title="fallback")
    assert parsed.blocks == [
        ParsedBlock("list_item", "- One"),
        ParsedBlock("list_item", "- Two"),
    ]


def test_ordered_list_to_list_items_with_distinguishable_markers() -> None:
    html = "<ol><li>One</li><li>Two</li></ol>"
    parsed = parse_html_note(html, fallback_title="fallback")
    assert parsed.blocks == [
        ParsedBlock("list_item", "1. One"),
        ParsedBlock("list_item", "2. Two"),
    ]


# ---------------------------------------------------------------------------
# Headings
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("level", [2, 3, 4, 5, 6])
def test_heading_levels_map_to_heading_blocks(level: int) -> None:
    html = f"<h{level}>Heading</h{level}>"
    parsed = parse_html_note(html, fallback_title="fallback")
    assert parsed.blocks == [ParsedBlock("heading", f"{'#' * level} Heading")]


# ---------------------------------------------------------------------------
# Links
# ---------------------------------------------------------------------------


def test_links_preserved_inline() -> None:
    html = '<p>See <a href="http://example.com">link</a> here</p>'
    parsed = parse_html_note(html, fallback_title="fallback")
    assert parsed.blocks == [
        ParsedBlock("paragraph", "See [link](http://example.com) here"),
    ]


# ---------------------------------------------------------------------------
# Table / image placeholders
# ---------------------------------------------------------------------------


def test_table_becomes_placeholder_paragraph_in_position() -> None:
    html = "<p>Before</p><table><tr><td>x</td></tr></table><p>After</p>"
    parsed = parse_html_note(html, fallback_title="fallback")
    assert parsed.blocks == [
        ParsedBlock("paragraph", "Before"),
        ParsedBlock("paragraph", "Skipped block: table"),
        ParsedBlock("paragraph", "After"),
    ]


def test_image_becomes_placeholder_paragraph_in_position() -> None:
    html = '<p>Before</p><img src="photo.png"><p>After</p>'
    parsed = parse_html_note(html, fallback_title="fallback")
    assert parsed.blocks == [
        ParsedBlock("paragraph", "Before"),
        ParsedBlock("paragraph", "Skipped block: image"),
        ParsedBlock("paragraph", "After"),
    ]


# ---------------------------------------------------------------------------
# Fallback paragraph handling
# ---------------------------------------------------------------------------


def test_unhandled_tag_becomes_paragraph() -> None:
    html = "<section>Just some text</section>"
    parsed = parse_html_note(html, fallback_title="fallback")
    assert parsed.blocks == [ParsedBlock("paragraph", "Just some text")]


def test_inline_style_and_class_are_ignored_without_placeholder() -> None:
    html = '<p class="foo" style="color:red">Styled text</p>'
    parsed = parse_html_note(html, fallback_title="fallback")
    assert parsed.blocks == [ParsedBlock("paragraph", "Styled text")]


# ---------------------------------------------------------------------------
# Container recursion (div/section wrapping structured content)
# ---------------------------------------------------------------------------


def test_container_recurses_into_headings_and_paragraphs() -> None:
    html = "<div><h2>Section</h2><p>Body text</p></div>"
    parsed = parse_html_note(html, fallback_title="fallback")
    assert parsed.blocks == [
        ParsedBlock("heading", "## Section"),
        ParsedBlock("paragraph", "Body text"),
    ]


def test_container_preserves_separate_paragraphs() -> None:
    html = "<div><p>First</p><p>Second</p></div>"
    parsed = parse_html_note(html, fallback_title="fallback")
    assert parsed.blocks == [
        ParsedBlock("paragraph", "First"),
        ParsedBlock("paragraph", "Second"),
    ]


def test_first_h1_consumed_as_title_when_nested_in_container() -> None:
    html = "<div><h1>Nested Title</h1><p>Body</p></div>"
    parsed = parse_html_note(html, fallback_title="fallback")
    assert parsed.title == "Nested Title"
    assert parsed.blocks == [ParsedBlock("paragraph", "Body")]


def test_loose_text_beside_block_child_in_container_is_not_preserved() -> None:
    html = "<div>Leading text<p>Nested para</p></div>"
    parsed = parse_html_note(html, fallback_title="fallback")
    assert parsed.blocks == [ParsedBlock("paragraph", "Nested para")]
