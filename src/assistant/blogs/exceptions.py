"""Blogs exceptions."""

from __future__ import annotations


class BlogsError(Exception):
    """Base exception for blogs."""


class BlogNotFoundError(BlogsError):
    """A directory, source or post does not exist or belongs to another user.

    The two cases are indistinguishable to the caller.
    """


class DuplicateDirectoryError(BlogsError):
    """The user already has a directory with this name."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"A directory named {name!r} already exists")


class DuplicateSourceError(BlogsError):
    """The user already registered this resolved feed."""

    def __init__(self) -> None:
        super().__init__("This blog is already registered")


class SourceResolutionError(BlogsError):
    """A URL could not be registered as a source.

    The message is shown to the user, so it is always generic and never
    contains anything from the fetched content.
    """


class InvalidPostQueryError(BlogsError):
    """A post list was asked for with a bad cursor or conflicting filters."""


class CollectionBusyError(BlogsError):
    """The job, or another refresh, is collecting right now."""

    def __init__(self) -> None:
        super().__init__("A collection is already running. Try again in a few minutes.")


class SourcePausedError(BlogsError):
    """A paused source can't be refreshed."""

    def __init__(self) -> None:
        super().__init__("Resume this blog to refresh it")


class FetchError(BlogsError):
    """A URL could not be fetched. The message never has response content."""


class BlockedUrlError(FetchError):
    """A URL is not allowed: bad scheme, credentials, or a non-public address."""
