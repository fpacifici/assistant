"""Pydantic schemas for Node endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class NodeCreate(BaseModel):
    payload: str
    after_node_id: uuid.UUID | None = None
    before_node_id: uuid.UUID | None = None
    block_type: str | None = None


class NodeUpdate(BaseModel):
    type: Literal["update"]
    payload: str
    expected_version: int
    block_type: str | None = None


class NodeMerge(BaseModel):
    type: Literal["merge"]
    source_node_id: uuid.UUID
    expected_version: int
    source_expected_version: int


NodePatch = Annotated[NodeUpdate | NodeMerge, Field(discriminator="type")]


class NodeSplit(BaseModel):
    offset: int = Field(ge=0)
    expected_version: int


class NodeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    note_id: uuid.UUID
    author_id: uuid.UUID
    node_type: str
    payload: str | None
    block_type: str | None = None
    version: int
    update_timestamp: datetime


class SplitResponse(BaseModel):
    original: NodeResponse
    new: NodeResponse
