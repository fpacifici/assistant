"""Tests for the google_auth oauth module."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest
import requests
from google.auth import exceptions as google_auth_exceptions

from assistant.config import Config
from assistant.google_auth.exceptions import (
    GoogleTokenExchangeError,
    GoogleTokenInvalidError,
)
from assistant.google_auth.oauth import (
    GoogleIdTokenClaims,
    build_authorization_url,
    exchange_code_for_tokens,
    redirect_uri,
    verify_id_token,
)


def _write_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, redirect_path: str | None = None
) -> Config:
    # The session-wide DOMAIN/PORT env vars (tests/conftest.py::_set_test_domain)
    # would otherwise override this file's own domain/port for every test here.
    monkeypatch.delenv("DOMAIN", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    lines = [
        "domain: example.com\n",
        "port: 8443\n",
        "google:\n",
        "  client_id: client-123.apps.googleusercontent.com\n",
        "  client_secret: secret-abc\n",
    ]
    if redirect_path is not None:
        lines.append(f"  redirect_path: {redirect_path}\n")
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text("".join(lines))
    return Config(config_path=config_file)


# --- redirect_uri ---


def test_redirect_uri_uses_default_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _write_config(tmp_path, monkeypatch)
    assert redirect_uri(config) == "https://example.com:8443/auth/google/callback"


def test_redirect_uri_uses_configured_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _write_config(tmp_path, monkeypatch, redirect_path="/custom/callback")
    assert redirect_uri(config) == "https://example.com:8443/custom/callback"


def test_redirect_uri_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _write_config(tmp_path, monkeypatch)
    with patch.dict(os.environ, {"GOOGLE_REDIRECT_PATH": "/env/callback"}):
        assert redirect_uri(config) == "https://example.com:8443/env/callback"


# --- build_authorization_url ---


def test_build_authorization_url_includes_required_params(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _write_config(tmp_path, monkeypatch)
    with patch("assistant.google_auth.oauth.Config", return_value=config):
        url = build_authorization_url(state="signed-state", nonce="the-nonce")

    parsed = urlparse(url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "accounts.google.com"
    params = parse_qs(parsed.query)
    assert params["client_id"] == ["client-123.apps.googleusercontent.com"]
    assert params["redirect_uri"] == [redirect_uri(config)]
    assert params["response_type"] == ["code"]
    scopes = params["scope"][0].split()
    assert set(scopes) == {"openid", "email", "profile"}
    assert params["state"] == ["signed-state"]
    assert params["nonce"] == ["the-nonce"]
    assert params["prompt"] == ["select_account"]


# --- exchange_code_for_tokens ---


def _make_response(
    *, ok: bool, status_code: int, json_data: dict | None = None, text: str = ""
) -> MagicMock:
    response = MagicMock(spec=requests.Response)
    response.ok = ok
    response.status_code = status_code
    response.text = text
    response.json.return_value = json_data or {}
    return response


def test_exchange_code_for_tokens_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _write_config(tmp_path, monkeypatch)
    with (
        patch("assistant.google_auth.oauth.Config", return_value=config),
        patch("assistant.google_auth.oauth.requests.post") as mock_post,
    ):
        mock_post.return_value = _make_response(
            ok=True, status_code=200, json_data={"id_token": "abc"}
        )
        result = exchange_code_for_tokens("auth-code")

    assert result == {"id_token": "abc"}


def test_exchange_code_for_tokens_non_2xx_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _write_config(tmp_path, monkeypatch)
    with (
        patch("assistant.google_auth.oauth.Config", return_value=config),
        patch("assistant.google_auth.oauth.requests.post") as mock_post,
    ):
        mock_post.return_value = _make_response(
            ok=False, status_code=400, text="bad request"
        )
        with pytest.raises(GoogleTokenExchangeError):
            exchange_code_for_tokens("auth-code")


def test_exchange_code_for_tokens_network_error_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _write_config(tmp_path, monkeypatch)
    with (
        patch("assistant.google_auth.oauth.Config", return_value=config),
        patch("assistant.google_auth.oauth.requests.post") as mock_post,
    ):
        mock_post.side_effect = requests.ConnectionError("boom")
        with pytest.raises(GoogleTokenExchangeError):
            exchange_code_for_tokens("auth-code")


# --- verify_id_token ---


def test_verify_id_token_valid_claims(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _write_config(tmp_path, monkeypatch)
    claims = {
        "sub": "1234567890",
        "email": "user@example.com",
        "email_verified": True,
        "given_name": "Ada",
        "family_name": "Lovelace",
        "nonce": "the-nonce",
    }
    with (
        patch("assistant.google_auth.oauth.Config", return_value=config),
        patch(
            "assistant.google_auth.oauth.google_id_token.verify_oauth2_token",
            return_value=claims,
        ),
    ):
        result = verify_id_token("raw-token", expected_nonce="the-nonce")

    assert result == GoogleIdTokenClaims(
        sub="1234567890",
        email="user@example.com",
        email_verified=True,
        given_name="Ada",
        family_name="Lovelace",
    )


def test_verify_id_token_missing_names_map_to_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _write_config(tmp_path, monkeypatch)
    claims = {
        "sub": "1234567890",
        "email": "user@example.com",
        "email_verified": True,
        "nonce": "the-nonce",
    }
    with (
        patch("assistant.google_auth.oauth.Config", return_value=config),
        patch(
            "assistant.google_auth.oauth.google_id_token.verify_oauth2_token",
            return_value=claims,
        ),
    ):
        result = verify_id_token("raw-token", expected_nonce="the-nonce")

    assert result.given_name is None
    assert result.family_name is None


def test_verify_id_token_library_error_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _write_config(tmp_path, monkeypatch)
    with (
        patch("assistant.google_auth.oauth.Config", return_value=config),
        patch(
            "assistant.google_auth.oauth.google_id_token.verify_oauth2_token",
            side_effect=google_auth_exceptions.GoogleAuthError("bad token"),
        ),
        pytest.raises(GoogleTokenInvalidError),
    ):
        verify_id_token("raw-token", expected_nonce="the-nonce")


def test_verify_id_token_nonce_mismatch_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _write_config(tmp_path, monkeypatch)
    claims = {
        "sub": "1234567890",
        "email": "user@example.com",
        "email_verified": True,
        "nonce": "wrong-nonce",
    }
    with (
        patch("assistant.google_auth.oauth.Config", return_value=config),
        patch(
            "assistant.google_auth.oauth.google_id_token.verify_oauth2_token",
            return_value=claims,
        ),
        pytest.raises(GoogleTokenInvalidError),
    ):
        verify_id_token("raw-token", expected_nonce="the-nonce")
