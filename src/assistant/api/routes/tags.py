"""Tag vocabulary API routes. Note-scoped tagging lives in notes.py."""

from __future__ import annotations

from fastapi import APIRouter, Response

from assistant.api.dependencies import CurrentUser, SessionDep
from assistant.api.schemas.tags import TagCreate, TagResponse
from assistant.notes.tags import find_or_create_tag, list_tags

router = APIRouter()


@router.get("", response_model=list[TagResponse])
def list_tags_endpoint(session: SessionDep, user: CurrentUser) -> list[TagResponse]:
    return [TagResponse.model_validate(t) for t in list_tags(session, user)]


@router.post(
    "",
    status_code=201,
    response_model=TagResponse,
    responses={200: {"model": TagResponse, "description": "Tag already existed"}},
)
def create_tag_endpoint(
    body: TagCreate,
    session: SessionDep,
    user: CurrentUser,
    response: Response,
) -> TagResponse:
    tag, created = find_or_create_tag(session, user, body.name)
    if not created:
        response.status_code = 200
    return TagResponse.model_validate(tag)
