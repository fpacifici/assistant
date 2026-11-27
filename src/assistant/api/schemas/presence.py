"""Pydantic schemas for presence and live note endpoints."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

from assistant.api.schemas.nodes import NodeResponse


class CursorSchema(BaseModel):
    """A caret: the node holding it and the character offset in that node."""

    model_config = ConfigDict(from_attributes=True)

    node_id: uuid.UUID
    offset: int = Field(ge=0)


class HeartbeatRequest(BaseModel):
    cursor: CursorSchema | None = None


class ActiveUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    name: str
    initial: str
    cursor: CursorSchema | None


class NotePresenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    note_id: uuid.UUID
    users: list[ActiveUserResponse]


class LiveNoteResponse(BaseModel):
    """`nodes` is null when the client already holds `revision`."""

    model_config = ConfigDict(from_attributes=True)

    revision: str
    title: str
    nodes: list[NodeResponse] | None
    presence: list[ActiveUserResponse]
