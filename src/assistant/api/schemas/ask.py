"""Pydantic schemas for the Ask AI endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MAX_QUESTION_LENGTH = 4000


class AskStatusResponse(BaseModel):
    """Whether Ask AI is available on this server."""

    enabled: bool


class ChatThreadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class SourceResponse(BaseModel):
    """A note an answer drew on."""

    note_id: uuid.UUID
    notebook_id: uuid.UUID
    title: str
    notebook_name: str


class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role: Literal["user", "assistant"]
    content: str
    sources: list[SourceResponse]


class ChatThreadDetailResponse(BaseModel):
    thread: ChatThreadResponse
    messages: list[ChatMessageResponse]


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_LENGTH)
