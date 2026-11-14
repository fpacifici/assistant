"""Analyzes reading links in the background, as soon as they are saved.

The service calls `queue_for_analysis` when it adds a link or resets one for
a retry. The ids are remembered on the session and, once the transaction
commits, handed to the registered listener: the API server's
`ReadingAnalysisWorker`. A rollback forgets them. Without a listener (AI
disabled, or the CLI) links simply stay `pending` until
`python -m assistant.cli.process_reading` runs.

The worker is one daemon thread, so only one link (and one PDF in memory) is
analyzed at a time. A failed attempt that leaves the link pending is queued
again after a delay (`RETRY_DELAYS`), and `LinkProcessor` marks the link
`failed` at its last attempt. Jobs still queued or waiting at shutdown are
dropped: those links stay pending for the CLI.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING

import sentry_sdk
from sqlalchemy import event
from sqlalchemy.orm import Session

from assistant.reading.analysis import Outcome

if TYPE_CHECKING:
    import uuid

logger = logging.getLogger(__name__)

AnalysisListener = Callable[[list["uuid.UUID"]], None]

# Seconds before the second and the third attempt.
RETRY_DELAYS = (30.0, 120.0)

_SESSION_KEY = "assistant.reading.links_to_analyze"
_listener: AnalysisListener | None = None


# --- After-commit announcements ---


def set_analysis_listener(listener: AnalysisListener | None) -> None:
    """Register the callable told about links to analyze after each commit.

    There is one listener per process (the API server's worker); `None`
    unregisters it.
    """
    global _listener  # noqa: PLW0603
    _listener = listener


def queue_for_analysis(session: Session, link_id: uuid.UUID) -> None:
    """Ask for a link to be analyzed once this transaction commits."""
    pending: set[uuid.UUID] = session.info.setdefault(_SESSION_KEY, set())
    pending.add(link_id)


@event.listens_for(Session, "after_commit")
def _announce_links(session: Session) -> None:
    pending: set[uuid.UUID] | None = session.info.pop(_SESSION_KEY, None)
    listener = _listener
    if not pending or listener is None:
        return
    try:
        listener(sorted(pending))
    except Exception:
        # The commit already happened; the links stay pending for the CLI.
        logger.exception("Could not schedule %d reading links", len(pending))


@event.listens_for(Session, "after_rollback")
def _forget_links(session: Session) -> None:
    session.info.pop(_SESSION_KEY, None)


# --- The worker ---


class ReadingAnalysisWorker:
    """Analyzes queued links one at a time on a background thread."""

    def __init__(
        self,
        process: Callable[[uuid.UUID], Outcome],
        retry_delays: tuple[float, ...] = RETRY_DELAYS,
    ) -> None:
        """Create a stopped worker.

        Args:
            process: Analyzes one link, usually `LinkProcessor.process`.
            retry_delays: Seconds to wait before each new attempt of a link
                that failed; the last one repeats.
        """
        self._process = process
        self._retry_delays = retry_delays
        self._queue: deque[uuid.UUID] = deque()
        self._pending: set[uuid.UUID] = set()
        self._retries: dict[uuid.UUID, int] = {}
        self._timers: dict[uuid.UUID, threading.Timer] = {}
        self._busy = False
        self._stopping = False
        self._condition = threading.Condition()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the thread and subscribe to links saved from now on."""
        with self._condition:
            if self._thread is not None:
                return
            self._stopping = False
            self._thread = threading.Thread(
                target=self._run, name="reading-analysis-worker", daemon=True
            )
            self._thread.start()
        set_analysis_listener(self.enqueue)

    def stop(self, timeout: float = 5.0) -> None:
        """Unsubscribe and stop after the current job; queued jobs are dropped."""
        set_analysis_listener(None)
        with self._condition:
            thread = self._thread
            self._stopping = True
            self._queue.clear()
            self._pending.clear()
            self._retries.clear()
            timers = list(self._timers.values())
            self._timers.clear()
            self._condition.notify_all()
        for timer in timers:
            timer.cancel()
        if thread is not None:
            thread.join(timeout)
        with self._condition:
            self._thread = None

    def enqueue(self, link_ids: Iterable[uuid.UUID]) -> None:
        """Queue links for analysis; a link already queued is not added twice.

        A link queued again by hand (a retry) no longer waits for its timer.
        """
        timers: list[threading.Timer] = []
        with self._condition:
            if self._stopping:
                return
            for link_id in link_ids:
                timer = self._timers.pop(link_id, None)
                if timer is not None:
                    timers.append(timer)
                if link_id not in self._pending:
                    self._pending.add(link_id)
                    self._queue.append(link_id)
            self._condition.notify_all()
        for timer in timers:
            timer.cancel()

    def wait_idle(self, timeout: float | None = None) -> bool:
        """Block until the queue is empty, no job runs and no retry waits.

        Returns:
            False if `timeout` expired first.
        """
        with self._condition:
            return self._condition.wait_for(
                lambda: not self._queue and not self._busy and not self._timers,
                timeout,
            )

    def _run(self) -> None:
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._queue or self._stopping)
                if self._stopping:
                    return
                link_id = self._queue.popleft()
                self._pending.discard(link_id)
                self._busy = True
            try:
                outcome = self._safe_process(link_id)
                self._after(link_id, outcome)
            finally:
                with self._condition:
                    self._busy = False
                    self._condition.notify_all()

    def _safe_process(self, link_id: uuid.UUID) -> Outcome:
        try:
            return self._process(link_id)
        except Exception as exc:
            # `LinkProcessor` records its own failures; this is the database.
            logger.warning("Could not process reading link %s", link_id, exc_info=True)
            sentry_sdk.capture_exception(exc)
            return Outcome.SKIPPED

    def _after(self, link_id: uuid.UUID, outcome: Outcome) -> None:
        with self._condition:
            if outcome is not Outcome.RETRY or self._stopping:
                self._retries.pop(link_id, None)
                return
            attempt = self._retries.get(link_id, 0)
            self._retries[link_id] = attempt + 1
            delay = self._retry_delays[min(attempt, len(self._retry_delays) - 1)]
            timer = threading.Timer(delay, self._retry, args=(link_id,))
            timer.daemon = True
            self._timers[link_id] = timer
            timer.start()

    def _retry(self, link_id: uuid.UUID) -> None:
        with self._condition:
            if self._timers.pop(link_id, None) is None:
                return
            if self._stopping or link_id in self._pending:
                self._condition.notify_all()
                return
            self._pending.add(link_id)
            self._queue.append(link_id)
            self._condition.notify_all()
