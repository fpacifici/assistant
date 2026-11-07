"""Manual refresh: collect one source now, from the API, in the background.

The refresh takes the job's advisory lock, so it never runs alongside the job
or another refresh, and answers at once with the run it created. The work
goes on in a thread of the API process, and the user follows it in the
collection log, which the pipeline writes as it goes.

A refresh killed with the process leaves its run unfinished; the next run
closes it as interrupted.
"""

from __future__ import annotations

import logging
import threading
from contextlib import ExitStack
from typing import TYPE_CHECKING

from assistant.blogs.analysis import create_post_analyzer
from assistant.blogs.exceptions import CollectionBusyError
from assistant.blogs.pipeline import BlogPipeline, advisory_lock
from assistant.blogs.runs import close_interrupted_runs, start_run
from assistant.blogs.text_store import create_text_store
from assistant.config import Config
from assistant.models.schema import BlogRunTrigger
from assistant.vectors.indexer import create_vector_indexer

if TYPE_CHECKING:
    import uuid
    from collections.abc import Callable
    from contextlib import AbstractContextManager

    from sqlalchemy.orm import Session, sessionmaker

    type SessionFactory = Callable[[], AbstractContextManager[Session]]
    type Executor = Callable[[Callable[[], None]], None]

logger = logging.getLogger(__name__)


def _in_thread(work: Callable[[], None]) -> None:
    threading.Thread(target=work, name="blog-refresh", daemon=True).start()


class BlogRefresher:
    """Starts manual refreshes of one source."""

    def __init__(
        self,
        session_factory: SessionFactory,
        lock: Callable[[], AbstractContextManager[bool]],
        pipeline_factory: Callable[[], BlogPipeline],
        executor: Executor = _in_thread,
    ) -> None:
        """Create a refresher.

        Args:
            session_factory: Opens database sessions.
            lock: Takes the job's advisory lock, see `advisory_lock`.
            pipeline_factory: A new pipeline for each refresh: a pipeline
                keeps state for one run.
            executor: Runs the work; a thread by default.
        """
        self._sessions = session_factory
        self._lock = lock
        self._pipelines = pipeline_factory
        self._executor = executor

    def start(self, source_id: uuid.UUID) -> uuid.UUID:
        """Start refreshing a source. The caller checked it is the user's.

        Returns:
            The run, already committed so it can be read at once.

        Raises:
            CollectionBusyError: If the job or another refresh is running.
        """
        stack = ExitStack()
        try:
            if not stack.enter_context(self._lock()):
                raise CollectionBusyError  # noqa: TRY301
            with self._sessions() as session:
                close_interrupted_runs(session)
                run_id = start_run(session, source_id, BlogRunTrigger.MANUAL).id
                session.commit()
            self._executor(lambda: self._work(source_id, run_id, stack))
        except BaseException:
            stack.close()
            raise
        return run_id

    def _work(self, source_id: uuid.UUID, run_id: uuid.UUID, stack: ExitStack) -> None:
        try:
            self._pipelines().run(source_id=source_id, refresh_run_id=run_id)
        except Exception:
            logger.exception("Could not refresh source %s", source_id)
        finally:
            stack.close()


def create_blog_refresher(
    session_factory: sessionmaker[Session], config: Config | None = None
) -> BlogRefresher | None:
    """Build the refresher from config, or `None` when AI is disabled."""
    config = config or Config()
    analyzer = create_post_analyzer(config)
    if analyzer is None:
        return None
    indexer = create_vector_indexer(config)
    text_store = create_text_store(config)
    max_posts = config.get_blogs_config()["max_posts_per_run"]
    engine = session_factory.kw["bind"]

    def pipeline() -> BlogPipeline:
        return BlogPipeline(
            session_factory,
            analyzer,
            indexer.embeddings if indexer else None,
            text_store,
            max_posts_per_run=max_posts,
        )

    return BlogRefresher(session_factory, lambda: advisory_lock(engine), pipeline)
