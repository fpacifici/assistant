"""Tests for the background worker that embeds notes after commit."""

from __future__ import annotations

import logging
import threading
import uuid
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from assistant.models.schema import User
from assistant.notes.service import create_note, create_notebook
from assistant.vectors import staleness
from assistant.vectors.indexer import IndexOutcome
from assistant.vectors.worker import VectorIndexWorker

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.orm import Session


class Recorder:
    """An index function recording the notes it was called with."""

    def __init__(self, fail_on: set[uuid.UUID] | None = None) -> None:
        self.indexed: list[uuid.UUID] = []
        self.fail_on = fail_on or set()
        self.started = threading.Event()
        self.release = threading.Event()
        self.release.set()

    def __call__(self, _session: Session, note_id: uuid.UUID) -> IndexOutcome:
        self.started.set()
        self.release.wait(5)
        if note_id in self.fail_on:
            msg = "insufficient_quota"
            raise RuntimeError(msg)
        self.indexed.append(note_id)
        return IndexOutcome.EMBEDDED


@pytest.fixture
def session_factory() -> MagicMock:
    return MagicMock()


@pytest.fixture
def recorder() -> Recorder:
    return Recorder()


@pytest.fixture
def worker(session_factory: MagicMock, recorder: Recorder) -> Iterator[VectorIndexWorker]:
    worker = VectorIndexWorker(session_factory, recorder)
    yield worker
    worker.stop()


# --- Processing ---


def test_indexes_queued_notes_in_order(
    worker: VectorIndexWorker,
    recorder: Recorder,
    session_factory: MagicMock,
) -> None:
    ids = [uuid.uuid4(), uuid.uuid4()]
    worker.start()

    worker.enqueue(ids)

    assert worker.wait_idle(5)
    assert recorder.indexed == ids
    session = session_factory.return_value.__enter__.return_value
    assert session.commit.call_count == 2


def test_repeated_saves_are_indexed_once(
    worker: VectorIndexWorker,
    recorder: Recorder,
) -> None:
    note_id = uuid.uuid4()

    worker.enqueue([note_id])
    worker.enqueue([note_id, note_id])
    worker.start()

    assert worker.wait_idle(5)
    assert recorder.indexed == [note_id]


def test_save_during_a_job_queues_the_note_again(
    worker: VectorIndexWorker,
    recorder: Recorder,
) -> None:
    note_id = uuid.uuid4()
    recorder.release.clear()
    worker.start()
    worker.enqueue([note_id])

    assert recorder.started.wait(5)
    worker.enqueue([note_id])
    recorder.release.set()

    assert worker.wait_idle(5)
    assert recorder.indexed == [note_id, note_id]


def test_failure_is_logged_and_reported_then_ignored(
    session_factory: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    broken, fine = uuid.uuid4(), uuid.uuid4()
    recorder = Recorder(fail_on={broken})
    worker = VectorIndexWorker(session_factory, recorder)
    worker.start()

    with (
        caplog.at_level(logging.WARNING, logger="assistant.vectors.worker"),
        patch("assistant.vectors.worker.sentry_sdk.capture_exception") as capture,
    ):
        worker.enqueue([broken, fine])
        assert worker.wait_idle(5)
    worker.stop()

    assert recorder.indexed == [fine]
    capture.assert_called_once()
    assert isinstance(capture.call_args.args[0], RuntimeError)
    [record] = caplog.records
    assert record.levelno == logging.WARNING
    assert str(broken) in record.getMessage()
    assert record.exc_info is not None


# --- Lifecycle ---


def test_start_subscribes_to_commits_and_stop_unsubscribes(
    worker: VectorIndexWorker,
    recorder: Recorder,
    db_session: Session,
) -> None:
    worker.start()
    owner = User(email="a@test.com", firstname="A", lastname="B")
    db_session.add(owner)
    db_session.flush()
    notebook = create_notebook(db_session, "NB", owner)
    note = create_note(db_session, notebook_id=notebook.id, owner=owner, title="T")

    db_session.commit()

    assert worker.wait_idle(5)
    assert recorder.indexed == [note.id]

    worker.stop()
    assert staleness._listener is None


def test_stop_drops_queued_jobs(worker: VectorIndexWorker, recorder: Recorder) -> None:
    worker.enqueue([uuid.uuid4()])

    worker.stop()
    worker.start()

    assert worker.wait_idle(5)
    assert recorder.indexed == []


def test_start_twice_runs_one_thread(worker: VectorIndexWorker) -> None:
    worker.start()
    thread = worker._thread

    worker.start()

    assert worker._thread is thread
