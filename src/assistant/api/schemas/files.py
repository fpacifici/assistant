"""Pydantic schemas for File endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FileCreate(BaseModel):
    note_id: uuid.UUID
    file_name: str


class FileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    note_id: uuid.UUID
    file_name: str
    state: str
    creation_timestamp: datetime
