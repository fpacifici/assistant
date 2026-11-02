"""Tests for calling the real Rust extension."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from assistant_rust import greet

# --- Round trip ---


def test_greet_returns_the_rust_result() -> None:
    assert greet("Ada") == "Hello, Ada!"


@pytest.mark.parametrize("name", ["Zoë 🐹", 'quo"te', "nul\x00byte", "<tag>&"])
def test_strings_cross_the_boundary_unchanged(name: str) -> None:
    assert greet(name) == f"Hello, {name}!"


def test_concurrent_calls() -> None:
    names = [f"user-{i}" for i in range(200)]

    with ThreadPoolExecutor(max_workers=8) as pool:
        greetings = list(pool.map(greet, names))

    assert greetings == [f"Hello, {name}!" for name in names]


# --- Errors ---


def test_rust_errors_are_raised() -> None:
    with pytest.raises(ValueError, match="name must not be empty"):
        greet("")
