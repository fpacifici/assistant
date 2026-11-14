"""Reading list exceptions."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid


class ReadingError(Exception):
    """Base exception for the reading list."""


class LinkNotFoundError(ReadingError):
    """A link does not exist or belongs to another user.

    The two cases are indistinguishable to the caller.
    """


class InvalidLinkUrlError(ReadingError):
    """The URL can't be saved: not an absolute http(s) URL."""

    def __init__(self) -> None:
        super().__init__("Enter an http or https URL")


class DuplicateLinkError(ReadingError):
    """The user already saved this URL, in any state."""

    def __init__(self, link_id: uuid.UUID) -> None:
        self.link_id = link_id
        super().__init__("This link is already in your reading list")


class InvalidLinkStateError(ReadingError):
    """The action is not valid from the link's current state."""


class InvalidLinkQueryError(ReadingError):
    """A link list was asked for with a bad cursor or conflicting filters."""
