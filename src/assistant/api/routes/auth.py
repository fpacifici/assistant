"""Authentication API routes."""

from __future__ import annotations

import secrets
import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError

from assistant.api.dependencies import CurrentUserId, SessionDep
from assistant.api.schemas.auth import (
    ConfirmationRequest,
    GoogleReauthStart,
    GoogleSwapInfo,
    GoogleSwapRequest,
    LoginRequest,
    RegisterRequest,
    RegisterResponse,
    SetPasswordRequest,
    UserResponse,
)
from assistant.auth.credentials import (
    get_auth_provider,
    swap_to_google,
    swap_to_password,
)
from assistant.auth.exceptions import (
    AccountNotConfirmedError,
    AuthError,
    CredentialSwapError,
)
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
    GoogleHandoffTokenInvalidError,
    GooglePasswordAccountExistsError,
    GoogleReauthMismatchError,
    GoogleStateInvalidError,
    GoogleTokenExchangeError,
    GoogleTokenInvalidError,
)
from assistant.google_auth.handoff import (
    REAUTH_TOKEN_TTL,
    SWAP_TOKEN_TTL,
    SwapClaims,
    sign_reauth_token,
    sign_swap_token,
    verify_reauth_token,
    verify_swap_token,
)
from assistant.google_auth.oauth import (
    build_authorization_url,
    exchange_code_for_tokens,
    verify_id_token,
)
from assistant.google_auth.service import handle_google_callback, verify_reauth
from assistant.google_auth.state import sign_state, verify_state
from assistant.invites.exceptions import (
    InviteEmailMismatchError,
    InviteNotUsableError,
    InvitesDisabledError,
    RegistrationDisabledError,
)
from assistant.notes.user_service import get_user

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from assistant.google_auth.oauth import GoogleIdTokenClaims
    from assistant.models.schema import User

router = APIRouter()

_ACCESS_MAX_AGE = 5 * 60
_REFRESH_MAX_AGE = 7 * 24 * 60 * 60

# Handoff cookies (see google_auth.handoff), each scoped to the only
# path that consumes it.
_SWAP_COOKIE = "google_swap"
_SWAP_COOKIE_PATH = "/auth/google/swap"
_REAUTH_COOKIE = "google_reauth"
_REAUTH_COOKIE_PATH = "/auth/credentials"


def _user_response(session: Session, user: User) -> UserResponse:
    response = UserResponse.model_validate(user)
    response.auth_provider = get_auth_provider(session, user.uid)
    return response


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


def _set_handoff_cookie(  # noqa: PLR0913
    request: Request,
    response: Response,
    *,
    name: str,
    value: str,
    path: str,
    max_age: int,
) -> None:
    response.set_cookie(
        name,
        value,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        max_age=max_age,
        path=path,
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
    return _user_response(session, user)


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
    return _user_response(session, user)


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
    return _user_response(session, user)


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


def _google_fail(config: Config, path: str, error_code: str) -> RedirectResponse:
    return _google_redirect(config, f"{path}?google_error={error_code}")


def _finish_google_reauth(
    session: Session,
    request: Request,
    config: Config,
    *,
    claims: GoogleIdTokenClaims,
    user_id: uuid.UUID,
) -> RedirectResponse:
    """Hand a successful re-authentication to the settings page."""
    try:
        verify_reauth(session, claims=claims, user_id=user_id)
    except GoogleReauthMismatchError:
        return _google_fail(config, "/settings", "reauth_mismatch")
    redirect = _google_redirect(config, "/settings?reauth=ok")
    _set_handoff_cookie(
        request,
        redirect,
        name=_REAUTH_COOKIE,
        value=sign_reauth_token(user_id=user_id),
        path=_REAUTH_COOKIE_PATH,
        max_age=int(REAUTH_TOKEN_TTL.total_seconds()),
    )
    return redirect


def _finish_google_login(
    session: Session,
    request: Request,
    config: Config,
    *,
    claims: GoogleIdTokenClaims,
    invite_id: uuid.UUID | None,
) -> RedirectResponse:
    fail_path = f"/invite/{invite_id}" if invite_id else "/login"
    try:
        user = handle_google_callback(session, claims=claims, invite_id=invite_id)
    except GoogleEmailNotVerifiedError:
        return _google_fail(config, fail_path, "unverified_email")
    except GooglePasswordAccountExistsError as exc:
        # Not a failure: offer converting the password account to Google.
        redirect = _google_redirect(config, "/login/switch-to-google")
        _set_handoff_cookie(
            request,
            redirect,
            name=_SWAP_COOKIE,
            value=sign_swap_token(user_id=exc.user_id, email=exc.email, sub=exc.sub),
            path=_SWAP_COOKIE_PATH,
            max_age=int(SWAP_TOKEN_TTL.total_seconds()),
        )
        return redirect
    except GoogleAccountCollisionError:
        return _google_fail(config, fail_path, "collision")
    except InviteEmailMismatchError:
        return _google_fail(config, fail_path, "invite_email_mismatch")
    except (InviteNotUsableError, InvitesDisabledError, RegistrationDisabledError):
        return _google_fail(config, fail_path, "registration_closed")

    access, refresh = issue_tokens(session, user.uid)
    redirect = _google_redirect(config, "/notebooks")
    _set_auth_cookies(request, redirect, access, refresh)
    return redirect


@router.get("/google/callback")
def google_callback(
    session: SessionDep,
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    config = Config()

    if error is not None:
        return _google_fail(config, "/login", "denied")
    if code is None or state is None:
        return _google_fail(config, "/login", "invalid_request")

    try:
        state_claims = verify_state(state)
    except GoogleStateInvalidError:
        return _google_fail(config, "/login", "invalid_state")

    try:
        tokens = exchange_code_for_tokens(code)
        id_claims = verify_id_token(tokens["id_token"], expected_nonce=state_claims.nonce)
    except (GoogleTokenExchangeError, GoogleTokenInvalidError):
        if state_claims.reauth_user_id is not None:
            fail_path = "/settings"
        elif state_claims.invite_id is not None:
            fail_path = f"/invite/{state_claims.invite_id}"
        else:
            fail_path = "/login"
        return _google_fail(config, fail_path, "google_failed")

    if state_claims.reauth_user_id is not None:
        return _finish_google_reauth(
            session,
            request,
            config,
            claims=id_claims,
            user_id=state_claims.reauth_user_id,
        )
    return _finish_google_login(
        session, request, config, claims=id_claims, invite_id=state_claims.invite_id
    )


# --- Credential swap ---


def _swap_claims_or_401(google_swap: str | None) -> SwapClaims:
    try:
        return verify_swap_token(google_swap)
    except GoogleHandoffTokenInvalidError as exc:
        raise HTTPException(
            status_code=401, detail="No pending switch to Google sign-in"
        ) from exc


@router.get("/google/swap", response_model=GoogleSwapInfo)
def google_swap_info(google_swap: str | None = Cookie(default=None)) -> GoogleSwapInfo:
    claims = _swap_claims_or_401(google_swap)
    return GoogleSwapInfo(email=claims.email)


@router.post("/google/swap", response_model=UserResponse)
def google_swap_confirm(
    body: GoogleSwapRequest,
    session: SessionDep,
    request: Request,
    response: Response,
    google_swap: str | None = Cookie(default=None),
) -> UserResponse:
    claims = _swap_claims_or_401(google_swap)
    try:
        user = swap_to_google(
            session,
            user_id=claims.user_id,
            email=claims.email,
            google_sub=claims.sub,
            password=body.password,
        )
    except AuthError as exc:
        raise HTTPException(status_code=401, detail="Invalid password") from exc
    except (CredentialSwapError, GoogleAccountCollisionError) as exc:
        raise HTTPException(
            status_code=409, detail="This account can no longer be switched"
        ) from exc

    response.delete_cookie(_SWAP_COOKIE, path=_SWAP_COOKIE_PATH)
    access, refresh = issue_tokens(session, user.uid)
    _set_auth_cookies(request, response, access, refresh)
    return _user_response(session, user)


@router.delete("/google/swap", status_code=204)
def google_swap_cancel(response: Response) -> Response:
    response.delete_cookie(_SWAP_COOKIE, path=_SWAP_COOKIE_PATH)
    response.status_code = 204
    return response


@router.post("/google/reauth", response_model=GoogleReauthStart)
def google_reauth_start(session: SessionDep, user_id: CurrentUserId) -> GoogleReauthStart:
    """Start a Google re-authentication of the current user.

    Returns the URL to navigate to rather than redirecting, so the
    frontend deals with an expired session before leaving the app.
    """
    if get_auth_provider(session, user_id) != "google":
        raise HTTPException(status_code=409, detail="Account doesn't use Google sign-in")
    nonce = secrets.token_urlsafe(16)
    state = sign_state(nonce=nonce, invite_id=None, reauth_user_id=user_id)
    return GoogleReauthStart(
        authorization_url=build_authorization_url(state=state, nonce=nonce)
    )


@router.post("/credentials/password", response_model=UserResponse)
def switch_to_password(  # noqa: PLR0913
    body: SetPasswordRequest,
    session: SessionDep,
    user_id: CurrentUserId,
    request: Request,
    response: Response,
    google_reauth: str | None = Cookie(default=None),
) -> UserResponse:
    try:
        reauth_user_id = verify_reauth_token(google_reauth)
    except GoogleHandoffTokenInvalidError:
        reauth_user_id = None
    if reauth_user_id != user_id:
        raise HTTPException(
            status_code=403, detail="Sign in with Google again to continue"
        )

    try:
        user = swap_to_password(session, user_id=user_id, password=body.password)
    except CredentialSwapError as exc:
        raise HTTPException(
            status_code=409, detail="Account already uses password sign-in"
        ) from exc

    response.delete_cookie(_REAUTH_COOKIE, path=_REAUTH_COOKIE_PATH)
    access, refresh = issue_tokens(session, user.uid)
    _set_auth_cookies(request, response, access, refresh)
    return _user_response(session, user)
