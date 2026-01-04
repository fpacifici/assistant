"""Shared pytest fixtures and configuration."""

from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Provide a temporary directory for tests.

    Args:
        tmp_path: pytest's temporary path fixture.

    Returns:
        Path to temporary directory.
    """
    return tmp_path


@pytest.fixture
def sample_file(temp_dir: Path) -> Iterator[Path]:
    """Create a sample file for testing.

    Args:
        temp_dir: Temporary directory fixture.

    Yields:
        Path to sample file.
    """
    file_path = temp_dir / "sample.txt"
    file_path.write_text("sample content\n")
    return file_path
    # Cleanup handled by tmp_path
