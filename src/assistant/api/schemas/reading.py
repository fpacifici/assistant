"""Pydantic schemas for reading list endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

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
    """A link. `title` is null until something names it: show the URL."""

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
    created_at: datetime
    decided_at: datetime | None


class LinkListResponse(BaseModel):
    links: list[LinkResponse]
    next_cursor: str | None


class CategoryCount(BaseModel):
    """How many links of a state one category has. `category_id: null` is Unfiled."""

    category_id: uuid.UUID | None
    count: int
