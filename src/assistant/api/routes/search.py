"""Search API routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from assistant.api.dependencies import CurrentUser, SessionDep
from assistant.api.routes.notes import _note_response
from assistant.api.schemas.pagination import Pagination
from assistant.api.schemas.search import (
    SearchNotebookResponse,
    SearchResponse,
    SearchResultResponse,
    SnippetResponse,
    SnippetSegmentResponse,
)
from assistant.notes.tags import tags_for_notes
from assistant.search.query import EmptySearchQueryError
from assistant.search.service import SearchSort, search
from assistant.search.snippets import SnippetSegment

router = APIRouter()


def _segments(segments: tuple[SnippetSegment, ...]) -> list[SnippetSegmentResponse]:
    return [
        SnippetSegmentResponse(text=s.text, highlighted=s.highlighted) for s in segments
    ]


@router.get("/notes", response_model=SearchResponse)
def search_notes_endpoint(
    q: Annotated[str, Query(description="Search string, see docs/specs/0007-search.md")],
    session: SessionDep,
    user: CurrentUser,
    pagination: Pagination,
    sort: SearchSort | None = None,
) -> SearchResponse:
    """Search the notes the caller can view by keyword and `tag:`."""
    try:
        results = search(
            session,
            user,
            q,
            offset=pagination.offset,
            limit=pagination.limit,
            sort=sort,
        )
    except EmptySearchQueryError:
        raise HTTPException(status_code=400, detail="Empty search query") from None

    tags_by_note = tags_for_notes(session, user, [hit.note.id for hit in results.hits])
    return SearchResponse(
        results=[
            SearchResultResponse(
                note=_note_response(
                    session, hit.note, user, tags_by_note.get(hit.note.id, [])
                ),
                notebook=SearchNotebookResponse(
                    id=hit.note.notebook.id,
                    name=hit.note.notebook.name,
                ),
                score=hit.score,
                title=_segments(hit.title_segments),
                snippets=[
                    SnippetResponse(node_id=s.node_id, segments=_segments(s.segments))
                    for s in hit.snippets
                ],
            )
            for hit in results.hits
        ],
        unknown_tags=results.unknown_tags,
        offset=pagination.offset,
        limit=pagination.limit,
    )
