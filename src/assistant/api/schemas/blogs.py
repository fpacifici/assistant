"""Pydantic schemas for blog endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from assistant.api.schemas.tags import TagResponse
from assistant.blogs.service import DEFAULT_LOOKBACK_DAYS, MAX_BULK_POSTS
from assistant.models.schema import BlogPostState

DirectoryName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
]
SourceTitle = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]
FreeText = Annotated[str, StringConstraints(max_length=10_000)]

# A look back this long reaches past any feed; the cap keeps the date valid.
MAX_LOOKBACK_DAYS = 36_500


class DirectoryCreate(BaseModel):
    name: DirectoryName


class DirectoryUpdate(BaseModel):
    name: DirectoryName


class DirectoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    created_at: datetime


class SourceCreate(BaseModel):
    url: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2048)
    ]
    title: SourceTitle | None = None
    remarks: FreeText | None = None
    preferences: FreeText | None = None
    directory_id: uuid.UUID | None = None
    lookback_days: int = Field(default=DEFAULT_LOOKBACK_DAYS, ge=0, le=MAX_LOOKBACK_DAYS)


class SourceUpdate(BaseModel):
    """A partial update. `directory_id: null` moves the source to Unfiled."""

    title: SourceTitle | None = None
    remarks: FreeText | None = None
    preferences: FreeText | None = None
    directory_id: uuid.UUID | None = None
    enabled: bool | None = None

    @model_validator(mode="after")
    def _no_null_for_required(self) -> SourceUpdate:
        for field in ("title", "enabled"):
            if field in self.model_fields_set and getattr(self, field) is None:
                msg = f"{field} must not be null"
                raise ValueError(msg)
        return self


class SourceResponse(BaseModel):
    """A source. `useful_post_count` is only set when reading a single source."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    directory_id: uuid.UUID | None
    url: str
    feed_url: str
    kind: str
    title: str
    remarks: str | None
    preferences: str | None
    collect_since: datetime
    enabled: bool
    archived_at: datetime | None
    last_fetched_at: datetime | None
    last_error: str | None
    consecutive_failures: int
    created_at: datetime
    useful_post_count: int | None = None


class PostResponse(BaseModel):
    """A post. A failed one has no summary, and possibly no title either."""

    id: uuid.UUID
    source_id: uuid.UUID
    source_title: str
    url: str
    title: str | None
    published_at: datetime
    summary: str | None
    match_level: str | None
    motivation: str | None
    status: str
    state: str
    evaluated_at: datetime | None
    read_at: datetime | None
    tags: list[TagResponse]


class PostListResponse(BaseModel):
    posts: list[PostResponse]
    next_cursor: str | None


class PostStateUpdate(BaseModel):
    state: BlogPostState


class PostReadUpdate(BaseModel):
    read: bool


class BulkPostStateUpdate(BaseModel):
    post_ids: Annotated[list[uuid.UUID], Field(min_length=1, max_length=MAX_BULK_POSTS)]
    state: BlogPostState


class BulkPostStateResponse(BaseModel):
    updated: int
