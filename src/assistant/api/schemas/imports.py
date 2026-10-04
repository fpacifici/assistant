"""Pydantic schemas for the notes-import endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ImportUploadResponse(BaseModel):
    import_id: uuid.UUID


class ImportRunRequest(BaseModel):
    include_web_clips: bool = False


class KeptNoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    note_id: uuid.UUID
    notebook_id: uuid.UUID
    title: str
    notebook: str
    source_path: str
    imported_at: datetime | None
    modified_at: datetime


class DuplicateNoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str
    notebook: str
    source_path: str


class FailedNoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_path: str
    error: str


class FailedNotebookResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    reason: str
    skipped_notes: int


class ImportReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    notebooks_touched: int
    created: int
    refreshed: int
    unchanged: int
    skipped_web_clip: int
    imported_web_clip: int
    kept_modified: list[KeptNoteResponse]
    kept_untracked: list[KeptNoteResponse]
    duplicate_title: list[DuplicateNoteResponse]
    failed: list[FailedNoteResponse]
    notebooks_failed: list[FailedNotebookResponse]
