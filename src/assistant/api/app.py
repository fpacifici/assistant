"""FastAPI application factory."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from assistant.api.dependencies import ImportSettings
from assistant.api.exceptions import register_exception_handlers
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

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


def create_app(
    session_factory: sessionmaker[Session] | None = None,
    file_storage: FileStorage | None = None,
    file_storage_path: Path | None = None,
    import_settings: ImportSettings | None = None,
) -> FastAPI:
    # First, so the SDK's FastAPI/Starlette/SQLAlchemy integrations are active
    # before anything below is built. No-op without a DSN (tests, local dev).
    init_sentry()

    app = FastAPI(title="Assistant API", version="0.1.0")

    if session_factory is None:
        from assistant.models.database import get_session_factory  # noqa: PLC0415

        session_factory = get_session_factory()
    app.state.session_factory = session_factory

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

    return app
