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


def test_multi_paragraph_list_item_separates_words() -> None:
    html = (
        '<ul><li><div class="list-content">'
        '<div class="para">first</div><div class="para">second</div>'
        "</div></li></ul>"
    )
    parsed = parse_html_note(html, fallback_title="fallback")
    assert parsed.blocks == [ParsedBlock("list_item", "- first second")]


def test_nested_div_inside_para_is_a_word_boundary() -> None:
    html = '<ul><li><div class="para">one<div>two</div>three</div></li></ul>'
    parsed = parse_html_note(html, fallback_title="fallback")
    assert parsed.blocks == [ParsedBlock("list_item", "- one two three")]


def test_inline_tags_inside_list_item_do_not_add_spaces() -> None:
    html = "<ul><li>un<u>der</u>line</li></ul>"
    parsed = parse_html_note(html, fallback_title="fallback")
    assert parsed.blocks == [ParsedBlock("list_item", "- underline")]


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
# Inline formatting
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tag", "marker"),
    [
        ("b", "**"),
        ("strong", "**"),
        ("i", "*"),
        ("em", "*"),
        ("s", "~~"),
        ("strike", "~~"),
        ("del", "~~"),
        ("code", "`"),
    ],
)
def test_inline_formatting_maps_to_markdown_markers(tag: str, marker: str) -> None:
    html = f"<p>a <{tag}>styled</{tag}> b</p>"
    parsed = parse_html_note(html, fallback_title="fallback")
    assert parsed.blocks == [ParsedBlock("paragraph", f"a {marker}styled{marker} b")]


def test_nested_bold_italic() -> None:
    parsed = parse_html_note("<p><b><i>x</i></b></p>", fallback_title="fallback")
    assert parsed.blocks == [ParsedBlock("paragraph", "***x***")]


def test_whitespace_moves_outside_markers() -> None:
    parsed = parse_html_note("<p>a<b> bold </b>b</p>", fallback_title="fallback")
    assert parsed.blocks == [ParsedBlock("paragraph", "a **bold** b")]


def test_empty_formatting_emits_nothing() -> None:
    parsed = parse_html_note("<p>a<b></b><i> </i>b</p>", fallback_title="fallback")
    assert parsed.blocks == [ParsedBlock("paragraph", "a b")]


def test_adjacent_same_formatting_is_merged() -> None:
    parsed = parse_html_note("<p><b>one</b><b>two</b></p>", fallback_title="fallback")
    assert parsed.blocks == [ParsedBlock("paragraph", "**onetwo**")]


def test_bold_only_paragraph_stays_a_paragraph() -> None:
    html = '<div class="para"><b>Section header</b></div>'
    parsed = parse_html_note(html, fallback_title="fallback")
    assert parsed.blocks == [ParsedBlock("paragraph", "**Section header**")]


def test_formatting_inside_list_item_and_heading() -> None:
    html = "<h2>A <i>title</i></h2><ul><li>an <b>item</b></li></ul>"
    parsed = parse_html_note(html, fallback_title="fallback")
    assert parsed.blocks == [
        ParsedBlock("heading", "## A *title*"),
        ParsedBlock("list_item", "- an **item**"),
    ]


def test_code_content_is_not_formatted_or_escaped() -> None:
    parsed = parse_html_note("<p><code>a*b <b>c</b>_d</code></p>", fallback_title="t")
    assert parsed.blocks == [ParsedBlock("paragraph", "`a*b c_d`")]


def test_code_containing_backtick_uses_longer_fence() -> None:
    parsed = parse_html_note("<p><code>a`b</code></p>", fallback_title="t")
    assert parsed.blocks == [ParsedBlock("paragraph", "``a`b``")]


def test_title_is_plain_text() -> None:
    parsed = parse_html_note("<h1>My <b>bold</b> *title*</h1>", fallback_title="t")
    assert parsed.title == "My bold *title*"


# ---------------------------------------------------------------------------
# Markdown escaping
# ---------------------------------------------------------------------------


def test_literal_markdown_characters_are_escaped() -> None:
    parsed = parse_html_note("<p>A[Ix, J] * B_c `d` ~e~</p>", fallback_title="t")
    assert parsed.blocks == [
        ParsedBlock("paragraph", r"A\[Ix, J\] \* B\_c \`d\` \~e\~"),
    ]


def test_literal_html_like_text_gets_a_zero_width_space() -> None:
    parsed = parse_html_note("<p>vector&lt;int&gt; a &lt; b a\\b</p>", fallback_title="t")
    assert parsed.blocks == [
        ParsedBlock("paragraph", "vector<\u200bint> a < b a\\\\b"),
    ]


@pytest.mark.parametrize(
    ("text", "payload"),
    [
        ("# not a heading", r"\# not a heading"),
        ("- not a list", r"\- not a list"),
        ("+ not a list", r"\+ not a list"),
        ("1. not a list", r"1\. not a list"),
        ("2) not a list", r"2\) not a list"),
        ("> not a quote", r"\> not a quote"),
        ("---", r"\---"),
        ("1.5 is a number", "1.5 is a number"),
        ("-5 degrees", r"\-5 degrees"),
    ],
)
def test_text_that_looks_like_block_markdown_is_escaped(text: str, payload: str) -> None:
    parsed = parse_html_note(f"<p>{text}</p>", fallback_title="t")
    assert parsed.blocks == [ParsedBlock("paragraph", payload)]


def test_list_item_text_that_looks_like_a_list_is_escaped() -> None:
    parsed = parse_html_note("<ul><li>- dash</li></ul>", fallback_title="t")
    assert parsed.blocks == [ParsedBlock("list_item", r"- \- dash")]


def test_link_url_is_not_escaped() -> None:
    html = '<p><a href="http://x.com/a_b*c">a_b</a></p>'
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks == [ParsedBlock("paragraph", r"[a\_b](http://x.com/a_b*c)")]


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


# ---------------------------------------------------------------------------
# Text next to block-level children is kept
# ---------------------------------------------------------------------------


def test_loose_text_beside_block_child_in_container_is_preserved() -> None:
    html = "<div>Leading text<p>Nested para</p></div>"
    parsed = parse_html_note(html, fallback_title="fallback")
    assert parsed.blocks == [
        ParsedBlock("paragraph", "Leading text"),
        ParsedBlock("paragraph", "Nested para"),
    ]


def test_mixed_text_and_block_children_keep_their_order() -> None:
    html = "<div>Before <u>under</u><p>Middle</p>after<div>Last</div></div>"
    parsed = parse_html_note(html, fallback_title="fallback")
    payloads = [b.payload for b in parsed.blocks]
    assert payloads == ["Before under", "Middle", "after", "Last"]


def test_top_level_loose_text_is_preserved() -> None:
    html = "Loose text<p>Para</p>"
    parsed = parse_html_note(html, fallback_title="fallback")
    assert [b.payload for b in parsed.blocks] == ["Loose text", "Para"]


def test_input_does_not_split_its_paragraph() -> None:
    html = '<div class="para"><input type="checkbox" class="en-todo"/>Buy milk</div>'
    parsed = parse_html_note(html, fallback_title="fallback")
    assert len(parsed.blocks) == 1
    assert "Buy milk" in parsed.blocks[0].payload


def test_legacy_checkbox_note_keeps_every_paragraph() -> None:
    checkbox = '<input type="checkbox" class="en-todo" checked="false"/>'
    items = "".join(f'<div class="para">{checkbox}Item {i}</div>' for i in range(4))
    html = f'<en-note class="peso">{items}</en-note>'
    parsed = parse_html_note(html, fallback_title="fallback")
    assert len(parsed.blocks) == 4
    assert all(f"Item {i}" in b.payload for i, b in enumerate(parsed.blocks))


def test_unknown_tag_without_block_children_is_inline() -> None:
    html = "<p>Some <custom-tag>custom</custom-tag> text</p>"
    parsed = parse_html_note(html, fallback_title="fallback")
    assert parsed.blocks == [ParsedBlock("paragraph", "Some custom text")]


def test_inline_tag_wrapping_blocks_keeps_paragraphs_separate() -> None:
    html = "<span><div>One</div><div>Two</div></span>"
    parsed = parse_html_note(html, fallback_title="fallback")
    assert [b.payload for b in parsed.blocks] == ["One", "Two"]


def test_html_comments_are_not_rendered() -> None:
    html = "<div>Text<!-- a comment --><p>Para</p></div>"
    parsed = parse_html_note(html, fallback_title="fallback")
    assert [b.payload for b in parsed.blocks] == ["Text", "Para"]
