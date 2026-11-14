"""Reading list API routes. Everything but HTTP work is in `assistant.reading.service`."""

from __future__ import annotations

import uuid
from typing import Annotated, cast

from fastapi import APIRouter, Query

from assistant.api.dependencies import CurrentUser, SessionDep
from assistant.api.schemas.reading import (
    CategoryCount,
    LinkCreate,
    LinkListResponse,
    LinkResponse,
    LinkUpdate,
)
from assistant.models.schema import ReadingLinkState
from assistant.reading.service import (
    LinkChanges,
    LinkFilters,
    add_link,
    delete_link,
    discard_link,
    get_link,
    link_counts,
    list_links,
    restore_link,
    update_link,
)

router = APIRouter()


@router.post("/link", status_code=201, response_model=LinkResponse)
def add_link_endpoint(
    body: LinkCreate, session: SessionDep, user: CurrentUser
) -> LinkResponse:
    """Save a link. It is analyzed in the background.

    409 with the existing link's `link_id` if the URL is already saved.
    """
    return LinkResponse.model_validate(add_link(session, user, body.url))


@router.get("/link", response_model=LinkListResponse)
def list_links_endpoint(  # noqa: PLR0913
    session: SessionDep,
    user: CurrentUser,
    state: Annotated[ReadingLinkState, Query()] = ReadingLinkState.TO_READ,
    category_id: Annotated[uuid.UUID | None, Query()] = None,
    unfiled: Annotated[bool, Query()] = False,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> LinkListResponse:
    """List the links of one state. Pass `next_cursor` back as `cursor`."""
    page = list_links(
        session,
        user,
        state=state,
        filters=LinkFilters(category_id=category_id, unfiled=unfiled),
        cursor=cursor,
        limit=limit,
    )
    return LinkListResponse(
        links=[LinkResponse.model_validate(link) for link in page.links],
        next_cursor=page.next_cursor,
    )


@router.get("/link/counts", response_model=list[CategoryCount])
def link_counts_endpoint(
    session: SessionDep,
    user: CurrentUser,
    state: Annotated[ReadingLinkState, Query()] = ReadingLinkState.TO_READ,
) -> list[CategoryCount]:
    """How many links of a state each category has. Empty categories are absent."""
    counts = link_counts(session, user, state)
    return [
        CategoryCount(category_id=category_id, count=count)
        for category_id, count in counts.items()
    ]


@router.get("/link/{link_id}", response_model=LinkResponse)
def get_link_endpoint(
    link_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> LinkResponse:
    """One of the caller's links, in any state."""
    return LinkResponse.model_validate(get_link(session, user, link_id))


@router.patch("/link/{link_id}", response_model=LinkResponse)
def update_link_endpoint(
    link_id: uuid.UUID,
    body: LinkUpdate,
    session: SessionDep,
    user: CurrentUser,
) -> LinkResponse:
    """Edit the title, category or notes. What the user sets wins over the analysis."""
    changes = cast("LinkChanges", body.model_dump(exclude_unset=True))
    return LinkResponse.model_validate(update_link(session, user, link_id, changes))


@router.post("/link/{link_id}/discard", response_model=LinkResponse)
def discard_link_endpoint(
    link_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> LinkResponse:
    """Move a link to the Archive. 409 unless it is to read."""
    return LinkResponse.model_validate(discard_link(session, user, link_id))


@router.post("/link/{link_id}/restore", response_model=LinkResponse)
def restore_link_endpoint(
    link_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> LinkResponse:
    """Move a discarded link back to read. 409 unless it is discarded."""
    return LinkResponse.model_validate(restore_link(session, user, link_id))


@router.delete("/link/{link_id}", status_code=204)
def delete_link_endpoint(
    link_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> None:
    """Delete a discarded or promoted link. 409 while it is to read."""
    delete_link(session, user, link_id)
