"""Pydantic schemas for reading list endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from assistant.models.schema import (
    ReadingAnalysisStatus,
    ReadingLinkState,
    ReadingLinkType,
)
from assistant.reading.service import MAX_TITLE_LENGTH, MAX_URL_LENGTH

LinkUrl = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_URL_LENGTH),
]
LinkTitle = Annotated[str, StringConstraints(max_length=MAX_TITLE_LENGTH)]
LinkNotes = Annotated[str, StringConstraints(max_length=10_000)]


class LinkCreate(BaseModel):
    url: LinkUrl


class LinkUpdate(BaseModel):
    """A partial update.

    `title: null` (or blank) goes back to the automatic title, and
    `category_id: null` moves the link to Unfiled. Both then win over the
    analysis.
    """

    title: LinkTitle | None = None
    category_id: uuid.UUID | None = None
    user_notes: LinkNotes | None = None


class LinkResponse(BaseModel):
    """A link. `title` is null until something names it: show the URL.

    `note_notebook_id` is the notebook of the promoted note, to link to it.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url: str
    title: str | None
    link_type: ReadingLinkType | None
    category_id: uuid.UUID | None
    summary: str | None
    user_notes: str | None
    analysis_status: ReadingAnalysisStatus
    last_error: str | None
    state: ReadingLinkState
    note_id: uuid.UUID | None
    note_notebook_id: uuid.UUID | None = None
    created_at: datetime
    decided_at: datetime | None


class LinkListResponse(BaseModel):
    links: list[LinkResponse]
    next_cursor: str | None


class CategoryCount(BaseModel):
    """How many links of a state one category has. `category_id: null` is Unfiled."""

    category_id: uuid.UUID | None
    count: int


NoteTitle = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]


class NoteSuggestionResponse(BaseModel):
    """A note the caller can edit, with the passage that matched."""

    model_config = ConfigDict(from_attributes=True)

    note_id: uuid.UUID
    notebook_id: uuid.UUID
    title: str
    notebook_name: str
    passage: str


class PromoteRequest(BaseModel):
    """Either an existing note, or a notebook and a title for a new one."""

    note_id: uuid.UUID | None = None
    notebook_id: uuid.UUID | None = None
    title: NoteTitle | None = None

    @model_validator(mode="after")
    def _one_target(self) -> PromoteRequest:
        new_note = self.notebook_id is not None and self.title is not None
        if (self.note_id is not None) == new_note or (
            self.note_id is not None and (self.notebook_id or self.title)
        ):
            msg = "Give note_id, or notebook_id and title"
            raise ValueError(msg)
        return self


class PromoteResponse(BaseModel):
    """The promoted link, and where its note is."""

    link: LinkResponse
    note_id: uuid.UUID
    notebook_id: uuid.UUID
