"""Tests for the free-text helpers."""

from __future__ import annotations

import pytest

from assistant.text import blank_to_none


@pytest.mark.parametrize(
    ("text", "expected"),
    [("  Databases ", "Databases"), ("", None), ("   \n", None), (None, None)],
)
def test_blank_to_none(text: str | None, expected: str | None) -> None:
    assert blank_to_none(text) == expected
