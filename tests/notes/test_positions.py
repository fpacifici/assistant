"""Tests for fractional indexing position generation."""

import pytest

from assistant.notes.positions import (
    generate_first_position,
    generate_n_positions,
    generate_position_between,
)


def test_generate_first_position() -> None:
    pos = generate_first_position()
    assert isinstance(pos, str)
    assert len(pos) > 0


def test_generate_position_at_end() -> None:
    first = generate_first_position()
    second = generate_position_between(first, None)
    assert second == "VV"
    assert second > first


def test_generate_position_at_start() -> None:
    first = generate_first_position()
    before = generate_position_between(None, first)
    assert before == "F"
    assert before < first


def test_generate_position_between_two() -> None:
    a = "V"
    b = "d"
    mid = generate_position_between(a, b)
    assert mid == "Z"
    assert a < mid < b


def test_generate_position_between_both_none() -> None:
    pos = generate_position_between(None, None)
    assert pos == generate_first_position()


def test_generate_position_between_adjacent() -> None:
    a = "a0"
    b = "a1"
    mid = generate_position_between(a, b)
    assert mid == "a0V"
    assert a < mid < b
    assert len(mid) > len(a)


def test_generate_position_invalid_order() -> None:
    with pytest.raises(ValueError, match=r"before.*must be less than.*after"):
        generate_position_between("b", "a")


def test_generate_position_equal_raises() -> None:
    with pytest.raises(ValueError, match=r"before.*must be less than.*after"):
        generate_position_between("a", "a")


def test_sequential_insertions_sort_correctly() -> None:
    positions = generate_n_positions(100)
    assert len(positions) == 100
    assert positions == sorted(positions)
    assert len(set(positions)) == 100


def test_repeated_bisection_between_neighbors() -> None:
    left = "V"
    right = "W"
    generated = []
    for _ in range(50):
        mid = generate_position_between(left, right)
        generated.append(mid)
        right = mid

    assert len(set(generated)) == 50
    all_positions = sorted({left, *generated, "W"})
    assert all_positions == sorted(all_positions)
    assert all_positions[0] == left
    assert all_positions[-1] == "W"


def test_generate_n_positions() -> None:
    positions = generate_n_positions(5)
    assert len(positions) == 5
    assert positions == sorted(positions)


def test_generate_n_positions_after() -> None:
    start = "V"
    positions = generate_n_positions(3, after=start)
    assert len(positions) == 3
    assert all(p > start for p in positions)
    assert positions == sorted(positions)


def test_generate_n_positions_zero() -> None:
    assert generate_n_positions(0) == []


def test_positions_interleave_correctly() -> None:
    """Build a list with inserts at various places and verify order."""
    positions = generate_n_positions(5)
    # Insert between first and second
    between_01 = generate_position_between(positions[0], positions[1])
    # Insert between third and fourth
    between_23 = generate_position_between(positions[2], positions[3])
    # Insert at start
    before_all = generate_position_between(None, positions[0])
    # Insert at end
    after_all = generate_position_between(positions[4], None)

    all_pos = [
        before_all,
        positions[0],
        between_01,
        positions[1],
        positions[2],
        between_23,
        positions[3],
        positions[4],
        after_all,
    ]
    assert all_pos == sorted(all_pos)
    assert len(set(all_pos)) == len(all_pos)
