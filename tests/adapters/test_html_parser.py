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


def test_empty_heading_emits_nothing() -> None:
    parsed = parse_html_note("<h1>Title</h1><h2> </h2><h3><br></h3>", fallback_title="t")
    assert parsed.blocks == []


def test_later_h1_becomes_level_one_heading() -> None:
    parsed = parse_html_note("<h1>Title</h1><h1>Section</h1>", fallback_title="t")
    assert parsed.title == "Title"
    assert parsed.blocks == [ParsedBlock("heading", "# Section")]


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


def test_web_clip_is_parsed_when_included() -> None:
    html = (
        '<meta itemprop="source" content="web.clip">'
        "<h1>Some clipped page</h1><p>content</p>"
    )
    parsed = parse_html_note(html, fallback_title="fallback", include_web_clips=True)
    assert parsed.skip is False
    assert parsed.web_clip is True
    assert parsed.title == "Some clipped page"
    assert parsed.blocks == [ParsedBlock("paragraph", "content")]


def test_skipped_web_clip_is_flagged_as_web_clip() -> None:
    html = '<meta itemprop="source" content="web.clip"><p>content</p>'
    parsed = parse_html_note(html, fallback_title="fallback")
    assert parsed.web_clip is True


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
# Nested lists
# ---------------------------------------------------------------------------


def _ul(*items: str, cls: str = "") -> str:
    class_attr = f' class="{cls}"' if cls else ""
    return f'<ul role="list"{class_attr}>{"".join(items)}</ul>'


def _item(text: str) -> str:
    return f'<li><div class="list-content"><div class="para">{text}</div></div></li>'


def test_sibling_nested_list_attaches_to_previous_item() -> None:
    html = _ul(_item("parent"), _ul(_item("child")), _item("next"))
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks == [
        ParsedBlock("list_item", "- parent\n  - child"),
        ParsedBlock("list_item", "- next"),
    ]


def test_three_levels_deep() -> None:
    html = _ul(_item("a"), _ul(_item("b"), _ul(_item("c"))))
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks == [ParsedBlock("list_item", "- a\n  - b\n    - c")]


def test_nested_list_inside_li() -> None:
    html = "<ul><li>a<ul><li>b</li></ul></li><li>c</li></ul>"
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks == [
        ParsedBlock("list_item", "- a\n  - b"),
        ParsedBlock("list_item", "- c"),
    ]


def test_nested_list_deep_inside_li_content_is_not_inlined() -> None:
    html = "<ul><li><div>a</div><div><ul><li>b</li></ul></div></li></ul>"
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks == [ParsedBlock("list_item", "- a\n  - b")]


def test_leading_nested_list_gets_an_empty_parent() -> None:
    html = _ul(_ul(_item("orphan")), _item("a"))
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks == [
        ParsedBlock("list_item", "- \n  - orphan"),
        ParsedBlock("list_item", "- a"),
    ]


def test_bullets_inside_numbered_list() -> None:
    html = "<ol><li>one</li><ul><li>x</li></ul><li>two</li></ol>"
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks == [
        ParsedBlock("list_item", "1. one\n   - x"),
        ParsedBlock("list_item", "2. two"),
    ]


def test_numbered_list_inside_bullets() -> None:
    html = "<ul><li>a</li><ol><li>x</li><li>y</li></ol></ul>"
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks == [ParsedBlock("list_item", "- a\n  1. x\n  2. y")]


def test_two_top_level_items_with_children_give_two_blocks() -> None:
    html = _ul(_item("a"), _ul(_item("a1")), _item("b"), _ul(_item("b1"), _item("b2")))
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks == [
        ParsedBlock("list_item", "- a\n  - a1"),
        ParsedBlock("list_item", "- b\n  - b1\n  - b2"),
    ]


def test_nested_items_keep_formatting_and_escaping() -> None:
    html = _ul(_item("a"), _ul(_item("<b>bold</b> 1. x"), _item("- y")))
    parsed = parse_html_note(html, fallback_title="t")
    payload = "- a\n  - **bold** 1. x\n  - \\- y"
    assert parsed.blocks == [ParsedBlock("list_item", payload)]


def test_todo_list_nesting() -> None:
    html = (
        '<ul class="en-todolist"><li data-checked="true">task</li>'
        '<ul class="en-todolist"><li data-checked="false">sub</li></ul>'
        "<ul><li>note</li></ul></ul>"
    )
    parsed = parse_html_note(html, fallback_title="t")
    payload = "- [x] task\n  - [ ] sub\n  - note"
    assert parsed.blocks == [ParsedBlock("list_item", payload)]


# ---------------------------------------------------------------------------
# Ordered list numbering
# ---------------------------------------------------------------------------


def test_nested_ordered_lists_number_each_level_separately() -> None:
    html = (
        "<ol><li>a</li><ol><li>a1</li><li>a2</li></ol>"
        "<li>b</li><ol><li>b1</li><li>b2</li></ol></ol>"
    )
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks == [
        ParsedBlock("list_item", "1. a\n   1. a1\n   2. a2"),
        ParsedBlock("list_item", "2. b\n   1. b1\n   2. b2"),
    ]


def test_ordered_list_start_is_respected() -> None:
    html = '<ol start="5"><li>five</li><li>six</li><ol start="3"><li>c</li></ol></ol>'
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks == [
        ParsedBlock("list_item", "5. five"),
        ParsedBlock("list_item", "6. six\n   3. c"),
    ]


@pytest.mark.parametrize("start", ["", "abc", "-1"])
def test_invalid_ordered_list_start_falls_back_to_one(start: str) -> None:
    parsed = parse_html_note(f'<ol start="{start}"><li>a</li></ol>', fallback_title="t")
    assert parsed.blocks == [ParsedBlock("list_item", "1. a")]


def test_nested_bullets_do_not_advance_the_numbered_counter() -> None:
    html = "<ol><li>a</li><ul><li>x</li><li>y</li></ul><li>b</li></ol>"
    parsed = parse_html_note(html, fallback_title="t")
    assert [b.payload.split("\n")[0] for b in parsed.blocks] == ["1. a", "2. b"]


def test_leading_nested_list_parent_is_not_numbered() -> None:
    html = "<ol><ol><li>x</li></ol><li>a</li><li>b</li></ol>"
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks == [
        ParsedBlock("list_item", "- \n  1. x"),
        ParsedBlock("list_item", "1. a"),
        ParsedBlock("list_item", "2. b"),
    ]


def test_empty_numbered_item_with_children_keeps_its_number() -> None:
    html = "<ol><li>a</li><li></li><ol><li>x</li></ol><li>b</li></ol>"
    parsed = parse_html_note(html, fallback_title="t")
    assert [b.payload for b in parsed.blocks] == ["1. a", "2. \n   1. x", "3. b"]


def test_ordered_item_width_sets_child_indent() -> None:
    items = "".join(f"<li>i{n}</li>" for n in range(1, 11))
    parsed = parse_html_note(f"<ol>{items}<ul><li>x</li></ul></ol>", fallback_title="t")
    assert parsed.blocks[-1] == ParsedBlock("list_item", "10. i10\n    - x")


# ---------------------------------------------------------------------------
# Empty list items
# ---------------------------------------------------------------------------


def test_trailing_empty_item_is_dropped() -> None:
    html = _ul(_item("a"), _item("<br>"))
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks == [ParsedBlock("list_item", "- a")]


def test_middle_empty_item_is_dropped_without_breaking_numbering() -> None:
    html = "<ol><li>a</li><li> </li><li>b</li></ol>"
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks == [
        ParsedBlock("list_item", "1. a"),
        ParsedBlock("list_item", "2. b"),
    ]


def test_empty_nested_item_is_dropped() -> None:
    html = _ul(_item("a"), _ul(_item(""), _item("b")))
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks == [ParsedBlock("list_item", "- a\n  - b")]


def test_empty_item_with_children_is_kept() -> None:
    html = _ul(_item("<br>"), _ul(_item("child")))
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks == [ParsedBlock("list_item", "- \n  - child")]


def test_empty_checklist_item_is_dropped() -> None:
    html = '<ul class="en-todolist"><li data-checked="false"><br></li></ul>'
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks == []


# ---------------------------------------------------------------------------
# Checklists
# ---------------------------------------------------------------------------

_BULLET_TODO = '<input type="checkbox" class="list-bullet-todo"/>'


def _li(text: str, checked: str | None = None) -> str:
    attr = f' data-checked="{checked}"' if checked is not None else ""
    return (
        f'<li{attr}><div class="list-bullet-todo-container">{_BULLET_TODO}</div>'
        f'<div class="list-content"><div class="para">{text}</div></div></li>'
    )


def test_todo_list_items_keep_checked_state() -> None:
    html = (
        f'<ul class="en-todolist" role="list">'
        f"{_li('done', 'true')}{_li('open', 'false')}</ul>"
    )
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks == [
        ParsedBlock("list_item", "- [x] done"),
        ParsedBlock("list_item", "- [ ] open"),
    ]


def test_plain_list_with_hidden_todo_input_has_no_checkbox() -> None:
    html = f'<ul role="list">{_li("plain")}</ul>'
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks == [ParsedBlock("list_item", "- plain")]


def test_plain_list_nested_in_todo_list_stays_plain() -> None:
    html = (
        f'<ul class="en-todolist" role="list">{_li("task", "false")}'
        f'<ul role="list">{_li("detail")}</ul></ul>'
    )
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks == [ParsedBlock("list_item", "- [ ] task\n  - detail")]


@pytest.mark.parametrize(("checked", "box"), [("true", "[x]"), ("false", "[ ]")])
def test_legacy_en_todo_paragraph_becomes_checklist_item(checked: str, box: str) -> None:
    html = (
        f'<div class="para"><input type="checkbox" class="en-todo" checked="{checked}"/>'
        "Buy *milk*</div>"
    )
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks == [ParsedBlock("list_item", f"- {box} Buy \\*milk\\*")]


def test_legacy_en_todo_without_checked_attribute_is_unchecked() -> None:
    html = '<div><input type="checkbox" class="en-todo"/>Task</div>'
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks == [ParsedBlock("list_item", "- [ ] Task")]


def test_legacy_en_todo_run_becomes_consecutive_items() -> None:
    html = "".join(
        f'<div class="para"><input class="en-todo" checked="{c}"/>{t}</div>'
        for c, t in [("true", "a"), ("false", "b")]
    )
    parsed = parse_html_note(f"<en-note>{html}</en-note>", fallback_title="t")
    assert parsed.blocks == [
        ParsedBlock("list_item", "- [x] a"),
        ParsedBlock("list_item", "- [ ] b"),
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


def test_link_without_text_is_dropped() -> None:
    html = (
        '<ul><li><a href="http://share"><svg></svg></a></li>'
        '<li>x <a href="u"> </a></li></ul>'
    )
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks == [ParsedBlock("list_item", "- x")]


def test_link_url_is_not_escaped() -> None:
    html = '<p><a href="http://x.com/a_b*c">a_b</a></p>'
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks == [ParsedBlock("paragraph", r"[a\_b](http://x.com/a_b*c)")]


# ---------------------------------------------------------------------------
# Tables and image placeholders
# ---------------------------------------------------------------------------


# --- Tables ---


def test_table_becomes_pipe_table_paragraph_in_position() -> None:
    html = (
        "<p>Before</p><table><tr><td>a</td><td>b</td></tr>"
        "<tr><td>1</td><td>2</td></tr></table><p>After</p>"
    )
    parsed = parse_html_note(html, fallback_title="fallback")
    assert parsed.blocks == [
        ParsedBlock("paragraph", "Before"),
        ParsedBlock("paragraph", "| a | b |\n| --- | --- |\n| 1 | 2 |"),
        ParsedBlock("paragraph", "After"),
    ]


def test_table_with_thead_and_tbody() -> None:
    html = (
        "<table><thead><tr><th>h1</th><th>h2</th></tr></thead>"
        "<tbody><tr><td>x</td><td>y</td></tr></tbody></table>"
    )
    parsed = parse_html_note(html, fallback_title="t")
    payload = "| h1 | h2 |\n| --- | --- |\n| x | y |"
    assert parsed.blocks == [ParsedBlock("paragraph", payload)]


def test_ragged_rows_are_padded() -> None:
    html = "<table><tr><td>a</td></tr><tr><td>1</td><td>2</td><td>3</td></tr></table>"
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks == [
        ParsedBlock("paragraph", "| a |  |  |\n| --- | --- | --- |\n| 1 | 2 | 3 |"),
    ]


def test_colspan_repeats_and_rowspan_leaves_empty_cells() -> None:
    html = (
        '<table><tr><td colspan="2">wide</td><td rowspan="2">tall</td></tr>'
        "<tr><td>a</td><td>b</td></tr></table>"
    )
    parsed = parse_html_note(html, fallback_title="t")
    payload = "| wide | wide | tall |\n| --- | --- | --- |\n| a | b |  |"
    assert parsed.blocks == [ParsedBlock("paragraph", payload)]


def test_cell_pipes_are_escaped_and_breaks_become_spaces() -> None:
    html = (
        "<table><tr><td>a | b<br>c</td></tr>"
        "<tr><td><div>x</div><div>y</div></td></tr></table>"
    )
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks == [ParsedBlock("paragraph", "| a \\| b c |\n| --- |\n| x y |")]


def test_cell_keeps_inline_formatting() -> None:
    html = '<table><tr><td><b>bold</b> <a href="http://x">l</a></td></tr></table>'
    parsed = parse_html_note(html, fallback_title="t")
    payload = "| **bold** [l](http://x) |\n| --- |"
    assert parsed.blocks == [ParsedBlock("paragraph", payload)]


def test_table_holding_tables_is_layout_and_recursed_into() -> None:
    html = (
        "<table><tr><td><p>intro</p>"
        "<table><tr><td>i1</td><td>i2</td></tr></table>"
        "</td><td>side</td></tr></table>"
    )
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks == [
        ParsedBlock("paragraph", "intro"),
        ParsedBlock("paragraph", "| i1 | i2 |\n| --- | --- |"),
        ParsedBlock("paragraph", "side"),
    ]


def test_evernote_wrapped_table() -> None:
    html = (
        '<en-table><div class="container"><table><tbody><tr>'
        '<td><div class="para">k</div></td><td><div class="para">v</div></td>'
        "</tr></tbody></table></div></en-table>"
    )
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks == [ParsedBlock("paragraph", "| k | v |\n| --- | --- |")]


def test_empty_table_emits_nothing() -> None:
    parsed = parse_html_note("<table></table>", fallback_title="t")
    assert parsed.blocks == []


def test_image_becomes_placeholder_paragraph_in_position() -> None:
    html = '<p>Before</p><img src="photo.png"><p>After</p>'
    parsed = parse_html_note(html, fallback_title="fallback")
    assert parsed.blocks == [
        ParsedBlock("paragraph", "Before"),
        ParsedBlock("paragraph", "Skipped block: image"),
        ParsedBlock("paragraph", "After"),
    ]


def _attachment_card(name: str) -> str:
    return (
        '<div data-resource-hash="abc123"><div data-type="application/pdf">'
        f'<svg><use href="#icon"></use></svg><div><div>{name}</div></div></div></div>'
    )


def test_attachment_card_becomes_placeholder_without_its_caption() -> None:
    html = f"<p>Before</p>{_attachment_card('Untitled Attachment')}<p>After</p>"
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks == [
        ParsedBlock("paragraph", "Before"),
        ParsedBlock("paragraph", "Skipped block: attachment"),
        ParsedBlock("paragraph", "After"),
    ]


def test_note_with_only_an_attachment_gives_one_placeholder() -> None:
    html = f'<en-note class="peso">{_attachment_card("paper.pdf")}</en-note>'
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks == [ParsedBlock("paragraph", "Skipped block: attachment")]


def test_attachment_card_splits_surrounding_text() -> None:
    html = f'<div class="para">see{_attachment_card("x.pdf")}here</div>'
    parsed = parse_html_note(html, fallback_title="t")
    assert [b.payload for b in parsed.blocks] == [
        "see",
        "Skipped block: attachment",
        "here",
    ]


def test_en_media_becomes_attachment_placeholder() -> None:
    html = '<p>a</p><en-media type="application/pdf" hash="abc"></en-media>'
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks[-1] == ParsedBlock("paragraph", "Skipped block: attachment")


def test_image_with_resource_hash_stays_an_image_placeholder() -> None:
    html = '<img data-resource-hash="abc" src="files/shot.png">'
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks == [ParsedBlock("paragraph", "Skipped block: image")]


def test_attachment_caption_inside_list_item_is_not_rendered() -> None:
    html = f"<ul><li>item{_attachment_card('Untitled Attachment')}</li></ul>"
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks == [ParsedBlock("list_item", "- item")]


# ---------------------------------------------------------------------------
# Code blocks, quotes, rules and media (common in web clips)
# ---------------------------------------------------------------------------


def test_pre_becomes_fenced_code_block_keeping_lines() -> None:
    html = "<pre>def f():\n    return *x*\n</pre>"
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks == [
        ParsedBlock("code_block", "```\ndef f():\n    return *x*\n```"),
    ]


def test_pre_with_br_and_code_language() -> None:
    html = '<pre><code class="language-python">a = 1<br>b = 2</code></pre>'
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks == [ParsedBlock("code_block", "```python\na = 1\nb = 2\n```")]


def test_code_block_containing_a_fence_uses_a_longer_fence() -> None:
    parsed = parse_html_note("<pre>```\nx\n```</pre>", fallback_title="t")
    assert parsed.blocks == [ParsedBlock("code_block", "````\n```\nx\n```\n````")]


def test_empty_pre_emits_nothing() -> None:
    parsed = parse_html_note("<pre>  \n</pre>", fallback_title="t")
    assert parsed.blocks == []


def test_evernote_codeblock_lines() -> None:
    html = (
        '<en-codeblock><div data-plaintext="true">first line</div>'
        '<div data-plaintext="true"><br></div>'
        '<div data-plaintext="true">  third &lt;line&gt;</div></en-codeblock>'
    )
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks == [
        ParsedBlock("code_block", "```\nfirst line\n\n  third <line>\n```"),
    ]


def test_blockquote_becomes_quote_block() -> None:
    html = "<blockquote>Quoted <b>text</b></blockquote>"
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks == [ParsedBlock("blockquote", "> Quoted **text**")]


def test_blockquote_with_several_paragraphs_is_one_block() -> None:
    html = "<blockquote><p>one</p><p>two</p></blockquote>"
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks == [ParsedBlock("blockquote", "> one\n>\n> two")]


def test_hr_emits_nothing() -> None:
    parsed = parse_html_note("<p>a</p><hr><p>b</p>", fallback_title="t")
    assert [b.payload for b in parsed.blocks] == ["a", "b"]


@pytest.mark.parametrize(
    "media",
    [
        '<iframe src="https://example.com/embed"></iframe>',
        '<video src="v.mp4">Your browser does not support video</video>',
        '<picture><source srcset="a.webp"></picture>',
        '<audio src="a.mp3"></audio>',
    ],
)
def test_media_becomes_attachment_placeholder(media: str) -> None:
    parsed = parse_html_note(f"<p>a</p>{media}", fallback_title="t")
    assert parsed.blocks == [
        ParsedBlock("paragraph", "a"),
        ParsedBlock("paragraph", "Skipped block: attachment"),
    ]


def test_figure_keeps_its_caption() -> None:
    html = '<figure><img src="x.png"><figcaption>A caption</figcaption></figure>'
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks == [
        ParsedBlock("paragraph", "Skipped block: image"),
        ParsedBlock("paragraph", "A caption"),
    ]


def test_svg_and_noscript_are_ignored() -> None:
    html = "<p>a<svg><text>icon</text></svg></p><noscript>enable js</noscript>"
    parsed = parse_html_note(html, fallback_title="t")
    assert parsed.blocks == [ParsedBlock("paragraph", "a")]


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
