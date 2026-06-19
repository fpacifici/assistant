"""FastAPI application factory."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI

from assistant.api.exceptions import register_exception_handlers
from assistant.api.routes.notebooks import router as notebooks_router
from assistant.api.routes.notes import router as notes_router
from assistant.api.routes.users import router as users_router

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


def create_app(
    session_factory: sessionmaker[Session] | None = None,
) -> FastAPI:
    app = FastAPI(title="Assistant API", version="0.1.0")

    if session_factory is None:
        from assistant.models.database import get_session_factory

        session_factory = get_session_factory()
    app.state.session_factory = session_factory

    register_exception_handlers(app)

    app.include_router(users_router, prefix="/user", tags=["users"])
    app.include_router(notebooks_router, prefix="/notebook", tags=["notebooks"])
    app.include_router(notes_router, prefix="/notebook", tags=["notes"])

    return app
