"""Shared FastAPI dependencies."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session


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


# TODO: return User entity instead of UUID when JWT auth is implemented,
# so we validate existence and load user data in one step.
def get_current_user_id(
    x_user_id: Annotated[str, Header()],
) -> uuid.UUID:
    try:
        return uuid.UUID(x_user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=401,
            detail="Invalid X-User-Id header",
        ) from exc


SessionDep = Annotated[Session, Depends(get_session)]
CurrentUserId = Annotated[uuid.UUID, Depends(get_current_user_id)]
