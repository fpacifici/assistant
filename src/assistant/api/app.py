"""FastAPI application factory."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from assistant.agents.rag import AskAgent, create_ask_agent
from assistant.agents.tracing import configure_tracing
from assistant.api.dependencies import ImportSettings
from assistant.api.exceptions import register_exception_handlers
from assistant.api.routes.ask import router as ask_router
from assistant.api.routes.auth import router as auth_router
from assistant.api.routes.files import router as files_router
from assistant.api.routes.imports import router as imports_router
from assistant.api.routes.invites import router as invites_router
from assistant.api.routes.nodes import router as nodes_router
from assistant.api.routes.notebooks import router as notebooks_router
from assistant.api.routes.notes import router as notes_router
from assistant.api.routes.search import router as search_router
from assistant.api.routes.tags import router as tags_router
from assistant.api.routes.users import router as users_router
from assistant.attachments.storage import FileStorage, LocalFileStorage
from assistant.config import Config
from assistant.observability import init_sentry
from assistant.vectors.indexer import create_vector_indexer
from assistant.vectors.worker import VectorIndexWorker

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.orm import Session, sessionmaker


def _default_vector_worker(
    session_factory: sessionmaker[Session],
) -> VectorIndexWorker | None:
    """The worker embedding notes after each write, or `None` if AI is off."""
    indexer = create_vector_indexer()
    if indexer is None:
        return None
    return VectorIndexWorker(session_factory, indexer.index_note)


def create_app(  # noqa: PLR0913
    session_factory: sessionmaker[Session] | None = None,
    file_storage: FileStorage | None = None,
    file_storage_path: Path | None = None,
    import_settings: ImportSettings | None = None,
    vector_worker: VectorIndexWorker | None = None,
    ask_agent: AskAgent | None = None,
) -> FastAPI:
    """Build the API application.

    Args:
        session_factory: Database sessions; defaults to the configured database.
        file_storage: Attachment storage; defaults to local files.
        file_storage_path: Root of the default local file storage.
        import_settings: Note-import upload settings; defaults to config.
        vector_worker: Embeds notes after their writes commit, started and
            stopped with the app. Defaults to one built from config, or none
            when AI is disabled (no `OPENAI_API_KEY`).
        ask_agent: The Ask AI agent. Defaults to one built from config, or
            none when AI is disabled (the /ask routes then answer 503).
    """
    # First, so the SDK's FastAPI/Starlette/SQLAlchemy integrations are active
    # before anything below is built. No-op without a DSN (tests, local dev).
    init_sentry()

    if session_factory is None:
        from assistant.models.database import get_session_factory  # noqa: PLC0415

        session_factory = get_session_factory()

    worker = vector_worker or _default_vector_worker(session_factory)
    configure_tracing()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if worker is not None:
            worker.start()
        try:
            yield
        finally:
            if worker is not None:
                worker.stop()

    app = FastAPI(title="Assistant API", version="0.1.0", lifespan=lifespan)
    app.state.session_factory = session_factory
    app.state.vector_worker = worker
    app.state.ask_agent = ask_agent or create_ask_agent(session_factory)

    if file_storage is None:
        storage_path = file_storage_path or Config().get_file_storage_path()
        storage_path.mkdir(parents=True, exist_ok=True)
        file_storage = LocalFileStorage(storage_path)
    app.state.file_storage = file_storage

    if import_settings is None:
        config = Config()
        import_settings = ImportSettings(
            storage_root=config.get_import_storage_path(),
            max_upload_bytes=config.get_import_max_upload_bytes(),
        )
    app.state.import_settings = import_settings

    # Behind the nginx-fronted deployment, the frontend and API share an origin and
    # this middleware never runs for browser traffic; it only matters for local dev
    # (Vite on :5173) and any other cross-origin caller. Override with a
    # comma-separated list when a cross-origin frontend is actually in play.
    cors_origins = [
        origin.strip()
        for origin in os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    app.include_router(auth_router, prefix="/auth", tags=["auth"])
    app.include_router(users_router, prefix="/user", tags=["users"])
    app.include_router(invites_router, prefix="/invites", tags=["invites"])
    app.include_router(notebooks_router, prefix="/notebook", tags=["notebooks"])
    app.include_router(notes_router, prefix="/notebook", tags=["notes"])
    app.include_router(nodes_router, prefix="/notebook", tags=["nodes"])
    app.include_router(files_router, tags=["files"])
    app.include_router(imports_router, prefix="/imports", tags=["imports"])
    app.include_router(tags_router, prefix="/tag", tags=["tags"])
    app.include_router(search_router, prefix="/search", tags=["search"])
    app.include_router(ask_router, prefix="/ask", tags=["ask"])

    return app
