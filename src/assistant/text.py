"""Small helpers for free text from users."""

from __future__ import annotations


def blank_to_none(text: str | None) -> str | None:
    """Trim free text; blank text means there is none."""
    stripped = text.strip() if text else ""
    return stripped or None
