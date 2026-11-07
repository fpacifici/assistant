"""Tests for the collection log helpers that need no database."""

from __future__ import annotations

from assistant.blogs.runs import MAX_LOGGED_ENTRIES, LoggedEntry, kept_for_log
from assistant.models.schema import BlogEntryVerdict

STORED = BlogEntryVerdict.STORED
NEW = BlogEntryVerdict.NEW


def _entries(*verdicts: BlogEntryVerdict) -> list[LoggedEntry]:
    return [LoggedEntry(url=f"https://x/{n}", verdict=v) for n, v in enumerate(verdicts)]


# --- Keeping entries ---


def test_everything_is_kept_under_the_limit() -> None:
    entries = _entries(STORED, NEW, STORED)
    assert kept_for_log(entries) == entries


def test_stored_entries_go_first_over_the_limit() -> None:
    entries = _entries(*[STORED] * MAX_LOGGED_ENTRIES, NEW, NEW)
    kept = kept_for_log(entries)
    assert len(kept) == MAX_LOGGED_ENTRIES
    assert kept[-2:] == entries[-2:]
    assert kept[: MAX_LOGGED_ENTRIES - 2] == entries[: MAX_LOGGED_ENTRIES - 2]


def test_the_order_of_the_source_is_kept() -> None:
    entries = _entries(NEW, *[STORED] * MAX_LOGGED_ENTRIES, NEW)
    kept = kept_for_log(entries)
    assert kept[0] == entries[0]
    assert kept[-1] == entries[-1]
    assert [e.url for e in kept] == sorted(
        (e.url for e in kept), key=lambda url: int(url.rsplit("/", 1)[1])
    )


def test_only_new_entries_still_stop_at_the_limit() -> None:
    entries = _entries(*[NEW] * (MAX_LOGGED_ENTRIES + 5))
    assert kept_for_log(entries) == entries[:MAX_LOGGED_ENTRIES]
