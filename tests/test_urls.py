"""Tests for the app-page link builders."""

from __future__ import annotations

import uuid
from unittest.mock import patch

from assistant.config import Config
from assistant.urls import confirm_email_url, invite_url, note_url, notebook_url


def _config() -> Config:
    # DOMAIN/PORT are set globally by the root conftest's _set_test_domain fixture.
    return Config()


def test_invite_url() -> None:
    invite_id = uuid.uuid4()
    assert invite_url(invite_id, _config()) == (
        f"https://test.example.com:8000/invite/{invite_id}"
    )


def test_confirm_email_url() -> None:
    assert confirm_email_url("tok123", _config()) == (
        "https://test.example.com:8000/confirm-email/tok123"
    )


def test_notebook_url() -> None:
    notebook_id = uuid.uuid4()
    assert notebook_url(notebook_id, _config()) == (
        f"https://test.example.com:8000/notebooks/{notebook_id}"
    )


def test_note_url() -> None:
    notebook_id = uuid.uuid4()
    note_id = uuid.uuid4()
    assert note_url(notebook_id, note_id, _config()) == (
        f"https://test.example.com:8000/notebooks/{notebook_id}/notes/{note_id}"
    )


def test_note_url_and_notebook_url_differ_for_same_notebook() -> None:
    notebook_id = uuid.uuid4()
    note_id = uuid.uuid4()
    assert note_url(notebook_id, note_id, _config()) != notebook_url(
        notebook_id, _config()
    )


def test_invite_url_uses_http_when_use_https_disabled() -> None:
    invite_id = uuid.uuid4()
    with patch.dict("os.environ", {"USE_HTTPS": "false"}):
        assert invite_url(invite_id, _config()) == (
            f"http://test.example.com:8000/invite/{invite_id}"
        )
