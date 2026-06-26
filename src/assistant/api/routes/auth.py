"""Authentication API routes."""

from __future__ import annotations

import os

from fastapi import APIRouter, Cookie, HTTPException, Response
from sqlalchemy.exc import IntegrityError

from assistant.api.dependencies import CurrentUserId, SessionDep
from assistant.api.schemas.auth import LoginRequest, RegisterRequest, UserResponse
from assistant.auth.service import (
    AuthError,
    authenticate_user,
    issue_tokens,
    logout_user,
    register_user,
    rotate_refresh_token,
)
from assistant.notes.user_service import get_user

router = APIRouter()

_COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
_ACCESS_MAX_AGE = 15 * 60
_REFRESH_MAX_AGE = 7 * 24 * 60 * 60


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    response.set_cookie(
        "access_token",
        access_token,
        httponly=True,
        samesite="lax",
        secure=_COOKIE_SECURE,
        max_age=_ACCESS_MAX_AGE,
        path="/",
    )
    response.set_cookie(
        "refresh_token",
        refresh_token,
        httponly=True,
        samesite="lax",
        secure=_COOKIE_SECURE,
        max_age=_REFRESH_MAX_AGE,
        path="/auth/refresh",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/auth/refresh")


@router.post("/register", status_code=201, response_model=UserResponse)
def register(
    body: RegisterRequest,
    session: SessionDep,
) -> UserResponse:
    try:
        user = register_user(
            session,
            email=body.email,
            password=body.password,
            firstname=body.firstname,
            lastname=body.lastname,
        )
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Email already registered") from exc
    return UserResponse.model_validate(user)


@router.post("/login", response_model=UserResponse)
def login(
    body: LoginRequest,
    session: SessionDep,
    response: Response,
) -> UserResponse:
    try:
        user = authenticate_user(session, email=body.email, password=body.password)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail="Invalid credentials") from exc

    access, refresh = issue_tokens(session, user.uid)
    _set_auth_cookies(response, access, refresh)
    return UserResponse.model_validate(user)


@router.post("/refresh", response_model=UserResponse)
def refresh(
    session: SessionDep,
    response: Response,
    refresh_token: str | None = Cookie(default=None),
) -> UserResponse:
    if refresh_token is None:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        user_id, new_access, new_refresh = rotate_refresh_token(session, refresh_token)
    except AuthError as exc:
        _clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    _set_auth_cookies(response, new_access, new_refresh)
    user = get_user(session, user_id)
    return UserResponse.model_validate(user)


@router.post("/logout", status_code=204)
def logout(
    session: SessionDep,
    response: Response,
    refresh_token: str | None = Cookie(default=None),
) -> Response:
    if refresh_token is not None:
        logout_user(session, refresh_token)
    _clear_auth_cookies(response)
    return Response(status_code=204)


@router.get("/me", response_model=UserResponse)
def me(
    session: SessionDep,
    user_id: CurrentUserId,
) -> UserResponse:
    user = get_user(session, user_id)
    return UserResponse.model_validate(user)
