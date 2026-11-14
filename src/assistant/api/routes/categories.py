"""Category API routes. Everything but HTTP work is in `assistant.categories.service`."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from assistant.api.dependencies import CurrentUser, SessionDep
from assistant.api.schemas.categories import (
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
)
from assistant.categories.service import (
    create_category,
    delete_category,
    list_categories,
    update_category,
)

router = APIRouter()


@router.get("", response_model=list[CategoryResponse])
def list_categories_endpoint(
    session: SessionDep, user: CurrentUser
) -> list[CategoryResponse]:
    """The caller's categories, by name."""
    return [CategoryResponse.model_validate(c) for c in list_categories(session, user)]


@router.post("", status_code=201, response_model=CategoryResponse)
def create_category_endpoint(
    body: CategoryCreate, session: SessionDep, user: CurrentUser
) -> CategoryResponse:
    """Create a category. 409 if the name is taken."""
    category = create_category(session, user, body.name, body.description)
    return CategoryResponse.model_validate(category)


@router.put("/{category_id}", response_model=CategoryResponse)
def update_category_endpoint(
    category_id: uuid.UUID,
    body: CategoryUpdate,
    session: SessionDep,
    user: CurrentUser,
) -> CategoryResponse:
    """Rename and describe a category. Nothing already filed is re-categorized."""
    category = update_category(session, user, category_id, body.name, body.description)
    return CategoryResponse.model_validate(category)


@router.delete("/{category_id}", status_code=204)
def delete_category_endpoint(
    category_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> None:
    """Delete a category. Its blog sources and links move to Unfiled."""
    delete_category(session, user, category_id)
