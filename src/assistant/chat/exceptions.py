"""Ask AI exceptions."""

from __future__ import annotations


class ChatError(Exception):
    """Base exception for Ask AI."""


class ChatThreadNotFoundError(ChatError):
    """Raised when a thread does not exist or belongs to another user."""


class AIDisabledError(ChatError):
    """Raised when an AI feature is used but no OpenAI API key is configured."""

    def __init__(self) -> None:
        super().__init__("AI features are disabled on this server")
