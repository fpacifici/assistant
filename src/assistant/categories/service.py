"""Categories of one user.

Blog sources and reading links are filed under them. Nothing is shared, so
there are no entitlements: every function takes the owner and loads rows
filtered by it, and someone else's category is simply not found. Nothing
commits: callers own the transaction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, select, update

from assistant.categories.exceptions import CategoryNotFoundError, DuplicateCategoryError
from assistant.models.schema import BlogSource, Category, ReadingLink
from assistant.text import blank_to_none

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session

    from assistant.models.schema import User


def list_categories(session: Session, owner: User) -> list[Category]:
    """Return `owner`'s categories, ordered by name, ignoring case."""
    stmt = (
        select(Category)
        .where(Category.owner_id == owner.uid)
        .order_by(func.lower(Category.name), Category.id)
    )
    return list(session.scalars(stmt))


def get_category(session: Session, owner: User, category_id: uuid.UUID) -> Category:
    """Return one of `owner`'s categories.

    Raises:
        CategoryNotFoundError: If it is missing or someone else's.
    """
    category = session.get(Category, category_id)
    if category is None or category.owner_id != owner.uid:
        raise CategoryNotFoundError(str(category_id))
    return category


def _require_free_name(
    session: Session,
    owner: User,
    name: str,
    *,
    ignore: uuid.UUID | None = None,
) -> None:
    existing = session.scalar(
        select(Category).where(Category.owner_id == owner.uid, Category.name == name),
    )
    if existing is not None and existing.id != ignore:
        raise DuplicateCategoryError(name)


def create_category(
    session: Session, owner: User, name: str, description: str | None = None
) -> Category:
    """Create a category.

    Raises:
        DuplicateCategoryError: If `owner` already has one with this name.
    """
    _require_free_name(session, owner, name)
    category = Category(
        owner_id=owner.uid, name=name, description=blank_to_none(description)
    )
    session.add(category)
    session.flush()
    return category


def update_category(
    session: Session,
    owner: User,
    category_id: uuid.UUID,
    name: str,
    description: str | None,
) -> Category:
    """Rename and describe a category.

    A new description applies to links analyzed from now on: nothing is
    re-categorized.

    Raises:
        CategoryNotFoundError: If it is missing or someone else's.
        DuplicateCategoryError: If `owner` has another one with this name.
    """
    category = get_category(session, owner, category_id)
    _require_free_name(session, owner, name, ignore=category.id)
    category.name = name
    category.description = blank_to_none(description)
    session.flush()
    return category


def delete_category(session: Session, owner: User, category_id: uuid.UUID) -> None:
    """Delete a category. What was filed under it moves to Unfiled.

    The foreign keys say `ON DELETE SET NULL` too; the explicit updates keep
    the session's objects and SQLite (which ignores foreign keys) in step.

    Raises:
        CategoryNotFoundError: If it is missing or someone else's.
    """
    category = get_category(session, owner, category_id)
    session.execute(
        update(BlogSource)
        .where(BlogSource.category_id == category.id)
        .values(category_id=None),
    )
    session.execute(
        update(ReadingLink)
        .where(ReadingLink.category_id == category.id)
        .values(category_id=None),
    )
    session.delete(category)
    session.flush()
