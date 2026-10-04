"""Pydantic schemas for Tag endpoints."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, model_validator


class TagResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class TagCreate(BaseModel):
    name: str


class NoteTagAdd(BaseModel):
    """Tag a note with an existing tag (`tag_id`) or by name (`name`).

    Tagging by name creates the tag on the fly when the caller has none
    with that name.
    """

    tag_id: uuid.UUID | None = None
    name: str | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> NoteTagAdd:
        if (self.tag_id is None) == (self.name is None):
            msg = "Exactly one of tag_id or name must be given"
            raise ValueError(msg)
        return self
