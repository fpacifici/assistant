"""Pydantic schemas for Notebook endpoints."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict


class NotebookCreate(BaseModel):
    name: str


class NotebookUpdate(BaseModel):
    name: str | None = None


class NotebookResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    owner_id: uuid.UUID
