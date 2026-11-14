"""Pydantic schemas for category endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

CategoryName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
]
CategoryDescription = Annotated[str, StringConstraints(max_length=2_000)]


class CategoryCreate(BaseModel):
    name: CategoryName
    description: CategoryDescription | None = None


class CategoryUpdate(BaseModel):
    """The whole category: a missing or blank description clears it."""

    name: CategoryName
    description: CategoryDescription | None = None


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
