"""Tests for calling the real Go library."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from assistant.golib import GoLibraryError, greet
from assistant.golib._library import call_string

# --- Round trip ---


def test_greet_returns_the_go_result() -> None:
    assert greet("Ada") == "Hello, Ada!"


@pytest.mark.parametrize("name", ["Zoë 🐹", 'quo"te', "nul\x00byte", "<tag>&"])
def test_strings_cross_the_boundary_unchanged(name: str) -> None:
    assert greet(name) == f"Hello, {name}!"


def test_concurrent_calls() -> None:
    names = [f"user-{i}" for i in range(200)]

    with ThreadPoolExecutor(max_workers=8) as pool:
        greetings = list(pool.map(greet, names))

    assert greetings == [f"Hello, {name}!" for name in names]


def test_many_calls_do_not_leak_or_crash() -> None:
    for i in range(10_000):
        assert greet(str(i)) == f"Hello, {i}!"


# --- Errors ---


def test_go_errors_are_raised() -> None:
    with pytest.raises(GoLibraryError, match="name must not be empty"):
        greet("")


def test_go_errors_are_value_errors() -> None:
    with pytest.raises(ValueError, match="name must not be empty"):
        greet("")


def test_undeclared_functions_are_rejected() -> None:
    with pytest.raises(RuntimeError, match="not declared"):
        call_string("AssistantMissing", "Ada")
