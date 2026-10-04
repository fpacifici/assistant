"""Tests for the google_auth handoff tokens."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from assistant.auth.exceptions import AuthError
from assistant.auth.service import create_access_token, decode_access_token
from assistant.google_auth.exceptions import GoogleHandoffTokenInvalidError
from assistant.google_auth.handoff import (
    SwapClaims,
    sign_reauth_token,
    sign_swap_token,
    verify_reauth_token,
    verify_swap_token,
)
from assistant.google_auth.state import sign_state

_JWT_SECRET = "test-jwt-secret-do-not-use-in-production"


@pytest.fixture(autouse=True)
def _set_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", _JWT_SECRET)


# --- Round trip ---


def test_swap_token_round_trip() -> None:
    user_id = uuid.uuid4()
    token = sign_swap_token(user_id=user_id, email="a@example.com", sub="sub-1")
    assert verify_swap_token(token) == SwapClaims(
        user_id=user_id, email="a@example.com", sub="sub-1"
    )


def test_reauth_token_round_trip() -> None:
    user_id = uuid.uuid4()
    assert verify_reauth_token(sign_reauth_token(user_id=user_id)) == user_id


# --- Invalid tokens ---


def test_missing_token_rejected() -> None:
    with pytest.raises(GoogleHandoffTokenInvalidError):
        verify_swap_token(None)


def test_expired_token_rejected() -> None:
    token = jwt.encode(
        {
            "purpose": "google_reauth",
            "user_id": str(uuid.uuid4()),
            "exp": datetime.now(UTC) - timedelta(seconds=1),
        },
        _JWT_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(GoogleHandoffTokenInvalidError):
        verify_reauth_token(token)


def test_tokens_are_not_interchangeable() -> None:
    user_id = uuid.uuid4()
    swap = sign_swap_token(user_id=user_id, email="a@example.com", sub="sub-1")
    reauth = sign_reauth_token(user_id=user_id)

    for token in (
        reauth,
        sign_state(nonce="n", invite_id=None),
        create_access_token(user_id),
    ):
        with pytest.raises(GoogleHandoffTokenInvalidError):
            verify_swap_token(token)
    with pytest.raises(GoogleHandoffTokenInvalidError):
        verify_reauth_token(swap)


def test_handoff_tokens_are_not_access_tokens() -> None:
    user_id = uuid.uuid4()
    # Even a same-secret token with a valid `sub` is refused unless it was
    # minted as an access token.
    sub_only = jwt.encode(
        {"sub": str(user_id), "exp": datetime.now(UTC) + timedelta(minutes=5)},
        _JWT_SECRET,
        algorithm="HS256",
    )

    for token in (
        sign_swap_token(user_id=user_id, email="a@example.com", sub="sub-1"),
        sign_reauth_token(user_id=user_id),
        sign_state(nonce="n", invite_id=None, reauth_user_id=user_id),
        sub_only,
    ):
        with pytest.raises(AuthError):
            decode_access_token(token)
    assert decode_access_token(create_access_token(user_id)) == user_id
