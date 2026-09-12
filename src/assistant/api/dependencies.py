"""Shared FastAPI dependencies."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from assistant.attachments.storage import FileStorage
from assistant.auth.exceptions import AuthError
from assistant.auth.service import decode_access_token
from assistant.models.schema import User
from assistant.notes.user_service import get_user


def get_session(
    request: Request,
) -> Generator[Session]:
    session_factory = request.app.state.session_factory
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_current_user_id(request: Request) -> uuid.UUID:
    """Resolve the authenticated user from a JWT access token.

    Accepts either an Authorization: Bearer header or an access_token cookie —
    never both simultaneously.
    """
    auth_header = request.headers.get("Authorization")
    access_cookie = request.cookies.get("access_token")

    if auth_header and access_cookie:
        raise HTTPException(
            status_code=401,
            detail="Ambiguous authentication: provide cookie or Bearer token, not both",
        )

    if auth_header:
        if not auth_header.startswith("Bearer "):
            raise HTTPException(
                status_code=401,
                detail="Authorization header must use the Bearer scheme",
            )
        token = auth_header[7:]
    elif access_cookie:
        token = access_cookie
    else:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        return decode_access_token(token)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def get_storage(request: Request) -> FileStorage:
    return request.app.state.file_storage  # type: ignore[no-any-return]


SessionDep = Annotated[Session, Depends(get_session)]
CurrentUserId = Annotated[uuid.UUID, Depends(get_current_user_id)]
StorageDep = Annotated[FileStorage, Depends(get_storage)]


def get_current_user(session: SessionDep, user_id: CurrentUserId) -> User:
    """Load the authenticated User row for the request.

    The actor in every notes-service call is a `User`, never a raw id — this
    is the one place per request that resolves the JWT-decoded id into that
    entity (also naturally 404s a token issued for a since-deleted user).
    """
    return get_user(session, user_id)


CurrentUser = Annotated[User, Depends(get_current_user)]
