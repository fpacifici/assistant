"""Tests for the google_auth state module."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from assistant.google_auth.exceptions import GoogleStateInvalidError
from assistant.google_auth.state import GoogleStateClaims, sign_state, verify_state

_JWT_SECRET = "test-jwt-secret-do-not-use-in-production"


@pytest.fixture(autouse=True)
def _set_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", _JWT_SECRET)


# --- Round trip ---


def test_sign_verify_round_trip_with_invite_id() -> None:
    invite_id = uuid.uuid4()
    state = sign_state(nonce="abc123", invite_id=invite_id)
    claims = verify_state(state)
    assert claims == GoogleStateClaims(nonce="abc123", invite_id=invite_id)


def test_sign_verify_round_trip_without_invite_id() -> None:
    state = sign_state(nonce="abc123", invite_id=None)
    claims = verify_state(state)
    assert claims == GoogleStateClaims(nonce="abc123", invite_id=None)


# --- Invalid state ---


def test_verify_state_garbage_string_raises() -> None:
    with pytest.raises(GoogleStateInvalidError):
        verify_state("not-a-valid-jwt")


def test_verify_state_wrong_secret_raises() -> None:
    payload = {
        "nonce": "abc123",
        "invite_id": None,
        "exp": datetime.now(UTC) + timedelta(minutes=10),
    }
    token = jwt.encode(payload, "a-different-secret", algorithm="HS256")
    with pytest.raises(GoogleStateInvalidError):
        verify_state(token)


def test_verify_state_expired_raises() -> None:
    payload = {
        "nonce": "abc123",
        "invite_id": None,
        "exp": datetime.now(UTC) - timedelta(minutes=1),
    }
    token = jwt.encode(payload, _JWT_SECRET, algorithm="HS256")
    with pytest.raises(GoogleStateInvalidError):
        verify_state(token)
