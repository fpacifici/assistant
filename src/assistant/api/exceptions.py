"""Exception-to-HTTP-response mapping."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from assistant.auth.exceptions import (
    ConfirmationCooldownError,
    ConfirmationLimitExceededError,
    ConfirmationNotFoundError,
    ConfirmationTokenInvalidError,
)
from assistant.invites.exceptions import (
    InviteEmailMismatchError,
    InviteNotUsableError,
    InvitePermissionError,
    InvitesDisabledError,
    QuotaExhaustedError,
    RegistrationDisabledError,
)
from assistant.notes.exceptions import (
    InvalidBlockTypeError,
    NodeVersionConflictError,
    NotesServiceError,
    PermissionDeniedError,
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

    @app.exception_handler(PermissionDeniedError)
    async def permission_denied_handler(
        request: Request,  # noqa: ARG001
        exc: PermissionDeniedError,
    ) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(exc)})

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

    @app.exception_handler(InviteNotUsableError)
    async def invite_not_usable_handler(
        request: Request,  # noqa: ARG001
        exc: InviteNotUsableError,  # noqa: ARG001
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": "Invite not found"})

    @app.exception_handler(InviteEmailMismatchError)
    async def invite_email_mismatch_handler(
        request: Request,  # noqa: ARG001
        exc: InviteEmailMismatchError,  # noqa: ARG001
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"detail": "Email does not match the invite"},
        )

    @app.exception_handler(InvitesDisabledError)
    async def invites_disabled_handler(
        request: Request,  # noqa: ARG001
        exc: InvitesDisabledError,  # noqa: ARG001
    ) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": "Invites are disabled"})

    @app.exception_handler(RegistrationDisabledError)
    async def registration_disabled_handler(
        request: Request,  # noqa: ARG001
        exc: RegistrationDisabledError,  # noqa: ARG001
    ) -> JSONResponse:
        return JSONResponse(
            status_code=403, content={"detail": "Registration is disabled"}
        )

    @app.exception_handler(QuotaExhaustedError)
    async def quota_exhausted_handler(
        request: Request,  # noqa: ARG001
        exc: QuotaExhaustedError,  # noqa: ARG001
    ) -> JSONResponse:
        return JSONResponse(
            status_code=403, content={"detail": "No invite quota remaining"}
        )

    @app.exception_handler(InvitePermissionError)
    async def invite_permission_denied_handler(
        request: Request,  # noqa: ARG001
        exc: InvitePermissionError,  # noqa: ARG001
    ) -> JSONResponse:
        return JSONResponse(
            status_code=403, content={"detail": "Not the sender of this invite"}
        )

    @app.exception_handler(ConfirmationTokenInvalidError)
    async def confirmation_token_invalid_handler(
        request: Request,  # noqa: ARG001
        exc: ConfirmationTokenInvalidError,  # noqa: ARG001
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404, content={"detail": "Confirmation link is invalid or expired"}
        )

    @app.exception_handler(ConfirmationNotFoundError)
    async def confirmation_not_found_handler(
        request: Request,  # noqa: ARG001
        exc: ConfirmationNotFoundError,  # noqa: ARG001
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404, content={"detail": "No pending registration for this email"}
        )

    @app.exception_handler(ConfirmationCooldownError)
    async def confirmation_cooldown_handler(
        request: Request,  # noqa: ARG001
        exc: ConfirmationCooldownError,  # noqa: ARG001
    ) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={"detail": "A confirmation email was sent recently — please wait"},
        )

    @app.exception_handler(ConfirmationLimitExceededError)
    async def confirmation_limit_exceeded_handler(
        request: Request,  # noqa: ARG001
        exc: ConfirmationLimitExceededError,  # noqa: ARG001
    ) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={"detail": "Too many confirmation attempts — please register again"},
        )
