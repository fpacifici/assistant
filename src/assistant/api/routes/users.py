"""User API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from assistant.api.dependencies import SessionDep
from assistant.api.schemas.pagination import Pagination
from assistant.api.schemas.users import UserCreate, UserResponse, UserUpdate
from assistant.notes.user_service import create_user, get_user, list_users, update_user

router = APIRouter()


@router.post("", status_code=201, response_model=UserResponse)
def create_user_endpoint(
    body: UserCreate,
    session: SessionDep,
) -> UserResponse:
    user = create_user(
        session,
        email=body.email,
        firstname=body.firstname,
        lastname=body.lastname,
    )
    return UserResponse.model_validate(user)


@router.get("", response_model=list[UserResponse])
def list_users_endpoint(
    session: SessionDep,
    pagination: Pagination,
) -> list[UserResponse]:
    users = list_users(
        session,
        offset=pagination.offset,
        limit=pagination.limit,
    )
    return [UserResponse.model_validate(u) for u in users]


@router.get("/{uid}", response_model=UserResponse)
def get_user_endpoint(
    uid: uuid.UUID,
    session: SessionDep,
) -> UserResponse:
    user = get_user(session, uid)
    return UserResponse.model_validate(user)


@router.patch("/{uid}", response_model=UserResponse)
def update_user_endpoint(
    uid: uuid.UUID,
    body: UserUpdate,
    session: SessionDep,
) -> UserResponse:
    user = update_user(
        session,
        uid,
        email=body.email,
        firstname=body.firstname,
        lastname=body.lastname,
    )
    return UserResponse.model_validate(user)
