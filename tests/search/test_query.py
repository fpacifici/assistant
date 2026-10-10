"""Tests for parsing a raw search string into a structured query."""

from __future__ import annotations

import pytest

from assistant.search.query import EmptySearchQueryError, parse_query

# --- Bare words ---


def test_bare_words_are_folded_terms() -> None:
    query = parse_query("Perché  Berlin ")

    assert query.terms == ("perche", "berlin")
    assert query.prefix is None


# --- Prefix (search while typing) ---


def test_last_word_without_trailing_space_is_a_prefix() -> None:
    query = parse_query("berlin Mün")

    assert query.terms == ("berlin",)
    assert query.prefix == "mun"


def test_single_character_last_word_is_a_plain_term() -> None:
    query = parse_query("berlin b")

    assert query.terms == ("berlin", "b")
    assert query.prefix is None


# --- Phrases ---


def test_quoted_words_are_a_phrase() -> None:
    query = parse_query('berlin "Project Plan" ')

    assert query.terms == ("berlin",)
    assert query.phrases == (("project", "plan"),)


def test_phrase_at_the_end_is_never_a_prefix() -> None:
    query = parse_query('"project plan"')

    assert query.phrases == (("project", "plan"),)
    assert query.prefix is None


def test_unterminated_quote_runs_to_the_end() -> None:
    query = parse_query('berlin "project plan')

    assert query.terms == ("berlin",)
    assert query.phrases == (("project", "plan"),)


def test_single_word_phrase_is_a_term() -> None:
    query = parse_query('"Berlin"')

    assert query.terms == ("berlin",)
    assert query.phrases == ()


# --- Tags ---


def test_tag_filters_are_normalized_keys() -> None:
    query = parse_query('TAG:Travel tag:"Road Trip" berlin ')

    assert query.tags == ("travel", "road trip")
    assert query.terms == ("berlin",)


def test_tag_at_the_end_is_not_a_prefix() -> None:
    query = parse_query("berlin tag:travel")

    assert query.terms == ("berlin",)
    assert query.tags == ("travel",)
    assert query.prefix is None


def test_empty_tag_is_ignored() -> None:
    assert parse_query('tag: tag:"" berlin ').tags == ()


def test_repeated_tag_is_kept_once() -> None:
    assert parse_query("tag:travel tag:Travel").tags == ("travel",)


# --- Empty queries ---


@pytest.mark.parametrize("raw", ["", "   ", '""', "tag:", "!!! ..."])
def test_query_with_nothing_to_search_is_rejected(raw: str) -> None:
    with pytest.raises(EmptySearchQueryError):
        parse_query(raw)


def test_tag_only_query_is_valid() -> None:
    assert parse_query("tag:travel").tags == ("travel",)
