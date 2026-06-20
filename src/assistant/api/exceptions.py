"""Exception-to-HTTP-response mapping."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from assistant.notes.exceptions import (
    InvalidBlockTypeError,
    NodeVersionConflictError,
    NotesServiceError,
    UserNotFoundError,
)

if TYPE_CHECKING:
    from fastapi import FastAPI, Request

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(UserNotFoundError)
    async def user_not_found_handler(
        request: Request,  # noqa: ARG001
        exc: UserNotFoundError,
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(InvalidBlockTypeError)
    async def invalid_block_type_handler(
        request: Request,  # noqa: ARG001
        exc: InvalidBlockTypeError,
    ) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(NodeVersionConflictError)
    async def version_conflict_handler(
        request: Request,  # noqa: ARG001
        exc: NodeVersionConflictError,
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(
        request: Request,  # noqa: ARG001
        exc: IntegrityError,  # noqa: ARG001
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"detail": "Conflict: duplicate or constraint violation"},
        )

    @app.exception_handler(NotesServiceError)
    async def notes_service_error_handler(
        request: Request,  # noqa: ARG001
        exc: NotesServiceError,
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})
