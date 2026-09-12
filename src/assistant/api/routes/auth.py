"""Authentication API routes."""

from __future__ import annotations

import secrets
import uuid

from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError

from assistant.api.dependencies import CurrentUserId, SessionDep
from assistant.api.schemas.auth import (
    ConfirmationRequest,
    LoginRequest,
    RegisterRequest,
    RegisterResponse,
    UserResponse,
)
from assistant.auth.exceptions import AccountNotConfirmedError, AuthError
from assistant.auth.service import (
    authenticate_user,
    confirm_email,
    issue_tokens,
    logout_user,
    register_user,
    resend_confirmation,
    rotate_refresh_token,
)
from assistant.config import Config
from assistant.google_auth.exceptions import (
    GoogleAccountCollisionError,
    GoogleEmailNotVerifiedError,
    GoogleStateInvalidError,
    GoogleTokenExchangeError,
    GoogleTokenInvalidError,
)
from assistant.google_auth.oauth import (
    build_authorization_url,
    exchange_code_for_tokens,
    verify_id_token,
)
from assistant.google_auth.service import handle_google_callback
from assistant.google_auth.state import sign_state, verify_state
from assistant.invites.exceptions import (
    InviteEmailMismatchError,
    InviteNotUsableError,
    InvitesDisabledError,
    RegistrationDisabledError,
)
from assistant.notes.user_service import get_user

router = APIRouter()

_ACCESS_MAX_AGE = 5 * 60
_REFRESH_MAX_AGE = 7 * 24 * 60 * 60


def _set_auth_cookies(
    request: Request, response: Response, access_token: str, refresh_token: str
) -> None:
    secure = request.url.scheme == "https"
    response.set_cookie(
        "access_token",
        access_token,
        httponly=True,
        samesite="lax",
        secure=secure,
        max_age=_ACCESS_MAX_AGE,
        path="/",
    )
    response.set_cookie(
        "refresh_token",
        refresh_token,
        httponly=True,
        samesite="lax",
        secure=secure,
        max_age=_REFRESH_MAX_AGE,
        path="/auth/refresh",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/auth/refresh")


@router.post("/register", status_code=201, response_model=RegisterResponse)
def register(body: RegisterRequest, session: SessionDep) -> RegisterResponse:
    try:
        user, email_sent = register_user(
            session,
            email=body.email,
            password=body.password,
            firstname=body.firstname,
            lastname=body.lastname,
            invite_id=body.invite_id,
        )
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Email already registered") from exc

    return RegisterResponse(email=user.email, confirmation_email_sent=email_sent)


@router.post("/login", response_model=UserResponse)
def login(
    body: LoginRequest,
    session: SessionDep,
    request: Request,
    response: Response,
) -> UserResponse:
    try:
        user = authenticate_user(session, email=body.email, password=body.password)
    except AccountNotConfirmedError as exc:
        raise HTTPException(
            status_code=403,
            detail="Account not confirmed — check your email or request a new link",
        ) from exc
    except AuthError as exc:
        raise HTTPException(status_code=401, detail="Invalid credentials") from exc

    access, refresh = issue_tokens(session, user.uid)
    _set_auth_cookies(request, response, access, refresh)
    return UserResponse.model_validate(user)


@router.post("/confirm-email/{token}", status_code=204)
def confirm_email_endpoint(token: str, session: SessionDep) -> Response:
    confirm_email(session, token)
    return Response(status_code=204)


@router.post("/resend-confirmation", status_code=204)
def resend_confirmation_endpoint(
    body: ConfirmationRequest, session: SessionDep
) -> Response:
    resend_confirmation(session, body.email)
    return Response(status_code=204)


@router.post("/refresh", response_model=UserResponse)
def refresh(
    session: SessionDep,
    request: Request,
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

    _set_auth_cookies(request, response, new_access, new_refresh)
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
    response.status_code = 204
    return response


@router.get("/me", response_model=UserResponse)
def me(
    session: SessionDep,
    user_id: CurrentUserId,
) -> UserResponse:
    user = get_user(session, user_id)
    return UserResponse.model_validate(user)


@router.get("/google")
def google_start(invite_id: uuid.UUID | None = None) -> RedirectResponse:
    nonce = secrets.token_urlsafe(16)
    state = sign_state(nonce=nonce, invite_id=invite_id)
    url = build_authorization_url(state=state, nonce=nonce)
    return RedirectResponse(url, status_code=302)


def _google_redirect(config: Config, path: str) -> RedirectResponse:
    """Absolute redirect back into the app, via config.public_origin() —
    the frontend is co-hosted with the API in production, so this is the
    app's single public origin either way."""
    url = f"{config.public_origin()}{path}"
    return RedirectResponse(url, status_code=302)


@router.get("/google/callback")
def google_callback(  # noqa: PLR0911
    session: SessionDep,
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    config = Config()

    def fail(path: str, error_code: str) -> RedirectResponse:
        return _google_redirect(config, f"{path}?google_error={error_code}")

    if error is not None:
        return fail("/login", "denied")
    if code is None or state is None:
        return fail("/login", "invalid_request")

    try:
        state_claims = verify_state(state)
    except GoogleStateInvalidError:
        return fail("/login", "invalid_state")

    fail_path = (
        f"/invite/{state_claims.invite_id}" if state_claims.invite_id else "/login"
    )

    try:
        tokens = exchange_code_for_tokens(code)
        id_claims = verify_id_token(tokens["id_token"], expected_nonce=state_claims.nonce)
    except (GoogleTokenExchangeError, GoogleTokenInvalidError):
        return fail(fail_path, "google_failed")

    try:
        user = handle_google_callback(
            session, claims=id_claims, invite_id=state_claims.invite_id
        )
    except GoogleEmailNotVerifiedError:
        return fail(fail_path, "unverified_email")
    except GoogleAccountCollisionError:
        return fail(fail_path, "collision")
    except InviteEmailMismatchError:
        return fail(fail_path, "invite_email_mismatch")
    except (InviteNotUsableError, InvitesDisabledError, RegistrationDisabledError):
        return fail(fail_path, "registration_closed")

    access, refresh = issue_tokens(session, user.uid)
    redirect = _google_redirect(config, "/notebooks")
    _set_auth_cookies(request, redirect, access, refresh)
    return redirect
