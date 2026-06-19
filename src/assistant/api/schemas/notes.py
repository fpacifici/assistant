"""Pydantic schemas for Note endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NoteCreate(BaseModel):
    title: str


class NoteUpdate(BaseModel):
    title: str | None = None


class NoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    notebook_id: uuid.UUID
    owner_id: uuid.UUID
    title: str
    creation_timestamp: datetime
    update_timestamp: datetime
