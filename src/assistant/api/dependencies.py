"""Shared FastAPI dependencies."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from assistant.auth.service import AuthError, decode_access_token


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


SessionDep = Annotated[Session, Depends(get_session)]
CurrentUserId = Annotated[uuid.UUID, Depends(get_current_user_id)]
