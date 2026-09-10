"""App-page link builders — the links this app embeds in outgoing email.

Not to be confused with the Mailgun API URL (email/service.py builds
that separately). Every link here shares the same {domain}:{port} base
from Config, so each new email-linked page gets one function here instead
of another inline f-string at its call site.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid

    from assistant.config import Config


def _base_url(config: Config) -> str:
    scheme = "https" if config.get_use_https() else "http"
    return f"{scheme}://{config.get_domain()}:{config.get_port()}"


def invite_url(invite_id: uuid.UUID, config: Config) -> str:
    """The accept-invite link — relocated from invites/service.py."""
    return f"{_base_url(config)}/invite/{invite_id}"


def confirm_email_url(token: str, config: Config) -> str:
    """The registration email-confirmation link."""
    return f"{_base_url(config)}/confirm-email/{token}"


def notebook_url(notebook_id: uuid.UUID, config: Config) -> str:
    """The link to a notebook, used in share notifications."""
    return f"{_base_url(config)}/notebooks/{notebook_id}"


def note_url(notebook_id: uuid.UUID, note_id: uuid.UUID, config: Config) -> str:
    """The link to a note, used in share notifications."""
    return f"{_base_url(config)}/notebooks/{notebook_id}/notes/{note_id}"
