"""Pydantic schemas for the search endpoint."""

from __future__ import annotations

import uuid

from pydantic import BaseModel

from assistant.api.schemas.notes import NoteResponse


class SnippetSegmentResponse(BaseModel):
    """A run of text; `highlighted` when it matched the query. Never HTML."""

    text: str
    highlighted: bool


class SnippetResponse(BaseModel):
    """A matching block of the note (open the note at `node_id`)."""

    node_id: uuid.UUID
    segments: list[SnippetSegmentResponse]


class SearchNotebookResponse(BaseModel):
    id: uuid.UUID
    name: str


class SearchResultResponse(BaseModel):
    note: NoteResponse
    notebook: SearchNotebookResponse
    score: float
    # The note title, split into segments with the matched words highlighted.
    title: list[SnippetSegmentResponse]
    snippets: list[SnippetResponse]


class SearchResponse(BaseModel):
    results: list[SearchResultResponse]
    # `tag:` filters naming a tag the caller doesn't have (results are empty).
    unknown_tags: list[str]
    offset: int
    limit: int
