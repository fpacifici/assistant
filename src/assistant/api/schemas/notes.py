"""Pydantic schemas for Note endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from assistant.api.schemas.tags import TagResponse
from assistant.models.schema import PermissionName

# As long as the `notes.title` column allows. Empty means untitled.
MAX_NOTE_TITLE_LENGTH = 500
NoteTitle = Annotated[str, StringConstraints(max_length=MAX_NOTE_TITLE_LENGTH)]


class NoteCreate(BaseModel):
    title: NoteTitle


class NoteUpdate(BaseModel):
    title: NoteTitle | None = None


class NoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    notebook_id: uuid.UUID
    owner_id: uuid.UUID
    title: str
    creation_timestamp: datetime
    update_timestamp: datetime
    permissions: list[PermissionName]
    # The caller's own tags on this note — tags are per user.
    tags: list[TagResponse]
    # Plain-text excerpt of the note's first blocks ("" for an empty note).
    preview: str
