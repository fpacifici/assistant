"""Tests for the process_blogs CLI."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from assistant.blogs.pipeline import RunReport
from assistant.cli import process_blogs
from assistant.cli.process_blogs import main


@contextmanager
def _lock(acquired: bool) -> Iterator[bool]:
    yield acquired


@pytest.fixture
def pipeline() -> Iterator[MagicMock]:
    with (
        patch.object(process_blogs, "BlogPipeline") as cls,
        patch.object(process_blogs, "get_engine"),
        patch.object(process_blogs, "create_post_analyzer", return_value=MagicMock()),
        patch.object(process_blogs, "create_vector_indexer", return_value=MagicMock()),
        patch.object(process_blogs, "advisory_lock", lambda _engine: _lock(True)),
    ):
        cls.return_value.run.return_value = RunReport()
        yield cls.return_value


def test_exits_0_on_success(pipeline: MagicMock) -> None:
    assert main([]) == 0
    pipeline.run.assert_called_once_with(user_id=None, source_id=None, dry_run=False)


def test_exits_1_if_anything_failed(pipeline: MagicMock) -> None:
    pipeline.run.return_value = RunReport(failures=1)
    assert main([]) == 1


def test_passes_the_filters(pipeline: MagicMock) -> None:
    user_id, source_id = uuid.uuid4(), uuid.uuid4()
    main(["--user-id", str(user_id), "--source-id", str(source_id), "--dry-run"])
    pipeline.run.assert_called_once_with(
        user_id=user_id, source_id=source_id, dry_run=True
    )


def test_exits_0_without_running_if_the_lock_is_held(pipeline: MagicMock) -> None:
    with patch.object(process_blogs, "advisory_lock", lambda _engine: _lock(False)):
        assert main([]) == 0
    pipeline.run.assert_not_called()


def test_exits_1_without_an_api_key(pipeline: MagicMock) -> None:
    with patch.object(process_blogs, "create_post_analyzer", return_value=None):
        assert main([]) == 1
    pipeline.run.assert_not_called()


def test_a_dry_run_needs_no_api_key(
    pipeline: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    pipeline.run.return_value = RunReport(would_collect=[("Blog", "https://x/1")])
    with patch.object(process_blogs, "create_post_analyzer", return_value=None):
        assert main(["--dry-run"]) == 0
    assert "Blog: https://x/1" in capsys.readouterr().out
