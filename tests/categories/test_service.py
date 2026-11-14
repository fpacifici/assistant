"""Tests for the category service, without the API."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

from assistant.categories.exceptions import CategoryNotFoundError, DuplicateCategoryError
from assistant.categories.service import (
    create_category,
    delete_category,
    get_category,
    list_categories,
    update_category,
)
from assistant.models.schema import BlogSource, User

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _user(session: Session, email: str) -> User:
    user = User(email=email, firstname="A", lastname="B")
    session.add(user)
    session.flush()
    return user


@pytest.fixture
def alice(db_session: Session) -> User:
    return _user(db_session, "alice@example.com")


@pytest.fixture
def bob(db_session: Session) -> User:
    return _user(db_session, "bob@example.com")


# --- Listing ---


def test_list_is_by_name_ignoring_case_and_per_owner(
    db_session: Session, alice: User, bob: User
) -> None:
    create_category(db_session, alice, "zebra")
    create_category(db_session, alice, "Apple")
    create_category(db_session, bob, "Bob's")
    assert [c.name for c in list_categories(db_session, alice)] == ["Apple", "zebra"]


# --- Creating and updating ---


def test_create_cleans_the_description(db_session: Session, alice: User) -> None:
    assert create_category(db_session, alice, "Tech", "  ").description is None
    assert (
        create_category(db_session, alice, "Food", " Recipes ").description == "Recipes"
    )


def test_names_are_unique_per_owner(db_session: Session, alice: User, bob: User) -> None:
    create_category(db_session, alice, "Tech")
    with pytest.raises(DuplicateCategoryError, match="already exists"):
        create_category(db_session, alice, "Tech")
    create_category(db_session, bob, "Tech")


def test_update_replaces_name_and_description(db_session: Session, alice: User) -> None:
    category = create_category(db_session, alice, "Tech", "Old")
    create_category(db_session, alice, "Other")
    with pytest.raises(DuplicateCategoryError):
        update_category(db_session, alice, category.id, "Other", None)
    updated = update_category(db_session, alice, category.id, "Tech", None)
    assert (updated.name, updated.description) == ("Tech", None)
    assert update_category(db_session, alice, category.id, "Tech", "New").description == (
        "New"
    )


# --- Ownership ---


def test_another_users_category_is_not_found(
    db_session: Session, alice: User, bob: User
) -> None:
    category = create_category(db_session, alice, "Tech")
    for call in (
        lambda: get_category(db_session, bob, category.id),
        lambda: update_category(db_session, bob, category.id, "x", None),
        lambda: delete_category(db_session, bob, category.id),
    ):
        with pytest.raises(CategoryNotFoundError):
            call()
    with pytest.raises(CategoryNotFoundError):
        get_category(db_session, alice, uuid.uuid4())


# --- Deleting ---


def test_delete_moves_sources_to_unfiled(db_session: Session, alice: User) -> None:
    category = create_category(db_session, alice, "Tech")
    source = BlogSource(
        owner_id=alice.uid,
        category_id=category.id,
        url="https://blog.example.com",
        feed_url="https://blog.example.com/feed",
        kind="feed",
        title="Blog",
        collect_since=category.created_at,
    )
    db_session.add(source)
    db_session.flush()
    delete_category(db_session, alice, category.id)
    db_session.refresh(source)
    assert source.category_id is None
    assert list_categories(db_session, alice) == []
