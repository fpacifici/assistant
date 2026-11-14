"""Category exceptions."""

from __future__ import annotations


class CategoriesError(Exception):
    """Base exception for categories."""


class CategoryNotFoundError(CategoriesError):
    """A category does not exist or belongs to another user.

    The two cases are indistinguishable to the caller.
    """


class DuplicateCategoryError(CategoriesError):
    """The user already has a category with this name."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"A category named {name!r} already exists")
