"""Tests for building highlighted snippets from a block's text."""

from __future__ import annotations

from assistant.search.query import parse_query
from assistant.search.snippets import SnippetSegment, build_segments


def _render(segments: tuple[SnippetSegment, ...]) -> str:
    """Show highlights as [brackets] so expectations read like the UI."""
    return "".join(f"[{s.text}]" if s.highlighted else s.text for s in segments)


# --- Highlighting ---


def test_highlights_matching_words_in_their_original_form() -> None:
    segments = build_segments("Perché no? Perche sì.", parse_query("perche "))

    assert _render(segments) == "[Perché] no? [Perche] sì."


def test_highlights_words_starting_with_the_prefix() -> None:
    segments = build_segments("Berliner in Berlin, not Bern", parse_query("berl"))

    assert _render(segments) == "[Berliner] in [Berlin], not Bern"


def test_highlights_phrase_words() -> None:
    segments = build_segments("The project plan", parse_query('"project plan"'))

    assert _render(segments) == "The [project] [plan]"


# --- Windowing ---

_BEFORE = " ".join(f"before{i}" for i in range(60))
_AFTER = " ".join(f"after{i}" for i in range(60))
_WORDS = set(_BEFORE.split()) | set(_AFTER.split()) | {"Berlin"}


def test_long_text_is_cut_around_the_first_match_on_word_boundaries() -> None:
    text = f"{_BEFORE} Berlin {_AFTER}"

    rendered = _render(build_segments(text, parse_query("berlin "), width=80))

    assert rendered.startswith("…")
    assert rendered.endswith("…")
    assert "[Berlin]" in rendered
    plain = rendered.strip("…").replace("[", "").replace("]", "")
    assert len(plain) <= 80
    assert set(plain.split()) <= _WORDS


def test_match_near_the_start_is_not_preceded_by_an_ellipsis() -> None:
    rendered = _render(
        build_segments(f"Berlin {_AFTER}", parse_query("berlin "), width=80)
    )

    assert rendered.startswith("[Berlin] after0")
    assert rendered.endswith("…")


def test_text_without_matches_shows_its_beginning() -> None:
    rendered = _render(build_segments(_AFTER, parse_query("berlin "), width=40))

    assert rendered.startswith("after0 after1")
    assert rendered.endswith("…")
    assert len(rendered) <= 41


def test_short_text_is_returned_whole() -> None:
    assert _render(build_segments("Hi Berlin", parse_query("berlin "))) == "Hi [Berlin]"
