"""Tests for the background analysis of reading links."""

from __future__ import annotations

import threading
import uuid
from typing import TYPE_CHECKING

import pytest

from assistant.models.schema import User
from assistant.reading import worker as worker_module
from assistant.reading.analysis import Outcome
from assistant.reading.service import add_link
from assistant.reading.worker import (
    ReadingAnalysisWorker,
    queue_for_analysis,
    set_analysis_listener,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.orm import Session


class Recorder:
    """A process function recording links, answering from a script of outcomes."""

    def __init__(self, outcomes: list[Outcome] | None = None) -> None:
        self.processed: list[uuid.UUID] = []
        self.outcomes = outcomes or []
        self.release = threading.Event()
        self.release.set()
        self.error: Exception | None = None

    def __call__(self, link_id: uuid.UUID) -> Outcome:
        self.release.wait(5)
        self.processed.append(link_id)
        if self.error is not None:
            raise self.error
        return self.outcomes.pop(0) if self.outcomes else Outcome.DONE


@pytest.fixture(autouse=True)
def _no_listener() -> Iterator[None]:
    yield
    set_analysis_listener(None)


def _started(
    recorder: Recorder, delays: tuple[float, ...] = (0.01,)
) -> ReadingAnalysisWorker:
    worker = ReadingAnalysisWorker(recorder, retry_delays=delays)
    worker.start()
    return worker


# --- Queue ---


def test_processes_queued_links() -> None:
    recorder = Recorder()
    worker = _started(recorder)
    ids = [uuid.uuid4(), uuid.uuid4()]
    worker.enqueue(ids)
    assert worker.wait_idle(5)
    assert recorder.processed == ids
    worker.stop()


def test_a_link_queued_twice_is_processed_once() -> None:
    recorder = Recorder()
    recorder.release.clear()
    worker = _started(recorder)
    first, second = uuid.uuid4(), uuid.uuid4()
    worker.enqueue([first])
    worker.enqueue([second, second])
    recorder.release.set()
    assert worker.wait_idle(5)
    assert recorder.processed == [first, second]
    worker.stop()


def test_an_unexpected_error_does_not_stop_the_worker() -> None:
    recorder = Recorder()
    recorder.error = RuntimeError("database down")
    worker = _started(recorder)
    worker.enqueue([uuid.uuid4()])
    assert worker.wait_idle(5)
    recorder.error = None
    link_id = uuid.uuid4()
    worker.enqueue([link_id])
    assert worker.wait_idle(5)
    assert recorder.processed[-1] == link_id
    worker.stop()


# --- Retries ---


def test_a_retry_is_queued_again_after_a_delay() -> None:
    recorder = Recorder([Outcome.RETRY, Outcome.RETRY, Outcome.FAILED])
    worker = _started(recorder)
    link_id = uuid.uuid4()
    worker.enqueue([link_id])
    assert worker.wait_idle(5)
    assert recorder.processed == [link_id] * 3
    worker.stop()


def test_queueing_by_hand_skips_the_wait() -> None:
    recorder = Recorder([Outcome.RETRY])
    worker = _started(recorder, delays=(60.0,))
    link_id = uuid.uuid4()
    worker.enqueue([link_id])
    assert not worker.wait_idle(0.2)  # a retry waits
    worker.enqueue([link_id])
    assert worker.wait_idle(5)
    assert recorder.processed == [link_id, link_id]
    worker.stop()


def test_stop_cancels_waiting_retries() -> None:
    recorder = Recorder([Outcome.RETRY])
    worker = _started(recorder, delays=(60.0,))
    worker.enqueue([uuid.uuid4()])
    assert not worker.wait_idle(0.2)
    worker.stop()
    assert worker.wait_idle(1)
    worker.enqueue([uuid.uuid4()])
    assert len(recorder.processed) == 1


# --- After commit ---


@pytest.fixture
def owner(db_session: Session) -> User:
    user = User(email="reader@example.com", firstname="R", lastname="R")
    db_session.add(user)
    db_session.flush()
    return user


def test_added_links_are_announced_after_commit(db_session: Session, owner: User) -> None:
    announced: list[list[uuid.UUID]] = []
    set_analysis_listener(announced.append)
    link = add_link(db_session, owner, "https://example.com/a")
    assert announced == []
    db_session.commit()
    assert announced == [[link.id]]


def test_a_rollback_forgets_them(db_session: Session, owner: User) -> None:
    announced: list[list[uuid.UUID]] = []
    set_analysis_listener(announced.append)
    add_link(db_session, owner, "https://example.com/a")
    db_session.rollback()
    db_session.commit()
    assert announced == []


def test_a_failing_listener_does_not_break_the_commit(
    db_session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    def broken(_ids: list[uuid.UUID]) -> None:
        msg = "queue full"
        raise RuntimeError(msg)

    set_analysis_listener(broken)
    queue_for_analysis(db_session, uuid.uuid4())
    db_session.commit()
    assert "Could not schedule" in caplog.text


def test_start_and_stop_subscribe_and_unsubscribe() -> None:
    worker = _started(Recorder())
    assert worker_module._listener == worker.enqueue
    worker.stop()
    assert worker_module._listener is None
