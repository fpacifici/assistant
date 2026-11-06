"""User API routes.

A user's profile (email, name, invite quota) is personal data, so every route
here requires authentication and only ever exposes or changes the caller's own
row. There is deliberately no list route and no create route: account creation
is `POST /auth/register`, and nothing may enumerate the user directory.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from assistant.api.dependencies import CurrentUser, SessionDep
from assistant.api.schemas.users import UserResponse, UserUpdate
from assistant.notes.user_service import update_user

router = APIRouter()


@router.get("/{uid}", response_model=UserResponse)
def get_user_endpoint(
    uid: uuid.UUID,
    user: CurrentUser,
) -> UserResponse:
    """Return the caller's own profile.

    Only the caller's own id is allowed; any other id is a 403, whether or
    not it exists, so this never confirms another account or leaks its data.
    """
    if uid != user.uid:
        raise HTTPException(status_code=403, detail="Cannot view another user's profile")
    return UserResponse.model_validate(user)


@router.patch("/{uid}", response_model=UserResponse)
def update_user_endpoint(
    uid: uuid.UUID,
    body: UserUpdate,
    session: SessionDep,
    user: CurrentUser,
) -> UserResponse:
    if uid != user.uid:
        raise HTTPException(
            status_code=403, detail="Cannot update another user's profile"
        )
    updated = update_user(
        session,
        uid,
        email=body.email,
        firstname=body.firstname,
        lastname=body.lastname,
    )
    return UserResponse.model_validate(updated)
