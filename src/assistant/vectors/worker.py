"""Background worker that embeds notes after their writes commit.

One daemon thread per process (the API server), fed by
`assistant.vectors.staleness` after every commit that marks notes stale.
Queued note ids are deduplicated, so a burst of autosaves on one note is
embedded once; an id is dropped from the pending set when its job *starts*,
so a save landing during the job queues the note again.

A failing job (no credits left, rate limits, network) is logged as a
warning, reported to Sentry and otherwise ignored: the note stays stale and
`reindex_search --vectors --stale-only` picks it up later. Jobs still queued
at shutdown are dropped for the same reason.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from typing import TYPE_CHECKING

import sentry_sdk

from assistant.vectors.staleness import set_stale_listener

if TYPE_CHECKING:
    import uuid
    from collections.abc import Callable, Iterable

    from sqlalchemy.orm import Session, sessionmaker

    from assistant.vectors.indexer import IndexOutcome

logger = logging.getLogger(__name__)


class VectorIndexWorker:
    """Embeds queued notes one at a time on a background thread."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        index_note: Callable[[Session, uuid.UUID], IndexOutcome],
    ) -> None:
        """Create a stopped worker.

        Args:
            session_factory: Each job runs in its own session and commits.
            index_note: Indexes one note, usually `VectorIndexer.index_note`.
        """
        self._session_factory = session_factory
        self._index_note = index_note
        self._queue: deque[uuid.UUID] = deque()
        self._pending: set[uuid.UUID] = set()
        self._busy = False
        self._stopping = False
        self._condition = threading.Condition()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the thread and subscribe to stale-note announcements."""
        with self._condition:
            if self._thread is not None:
                return
            self._stopping = False
            self._thread = threading.Thread(
                target=self._run,
                name="vector-index-worker",
                daemon=True,
            )
            self._thread.start()
        set_stale_listener(self.enqueue)

    def stop(self, timeout: float = 5.0) -> None:
        """Unsubscribe and stop after the current job; queued jobs are dropped."""
        set_stale_listener(None)
        with self._condition:
            thread = self._thread
            self._stopping = True
            self._queue.clear()
            self._pending.clear()
            self._condition.notify_all()
        if thread is not None:
            thread.join(timeout)
        with self._condition:
            self._thread = None

    def enqueue(self, note_ids: Iterable[uuid.UUID]) -> None:
        """Queue notes for embedding; notes already queued are not added twice."""
        with self._condition:
            for note_id in note_ids:
                if note_id not in self._pending:
                    self._pending.add(note_id)
                    self._queue.append(note_id)
            self._condition.notify_all()

    def wait_idle(self, timeout: float | None = None) -> bool:
        """Block until the queue is empty and no job runs.

        Returns:
            False if `timeout` expired first.
        """
        with self._condition:
            return self._condition.wait_for(
                lambda: not self._queue and not self._busy,
                timeout,
            )

    def _run(self) -> None:
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._queue or self._stopping)
                if self._stopping:
                    return
                note_id = self._queue.popleft()
                self._pending.discard(note_id)
                self._busy = True
            try:
                self._process(note_id)
            finally:
                with self._condition:
                    self._busy = False
                    self._condition.notify_all()

    def _process(self, note_id: uuid.UUID) -> None:
        try:
            with self._session_factory() as session:
                self._index_note(session, note_id)
                session.commit()
        except Exception as exc:
            logger.warning(
                "Could not embed note %s; it stays stale until a reindex",
                note_id,
                exc_info=True,
            )
            sentry_sdk.capture_exception(exc)
