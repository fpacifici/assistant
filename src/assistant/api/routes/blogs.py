"""Blog API routes. Everything but HTTP work is in `assistant.blogs.service`."""

from __future__ import annotations

import uuid
from typing import Annotated, cast

from fastapi import APIRouter, Query

from assistant.api.dependencies import CurrentUser, SessionDep
from assistant.api.schemas.blogs import (
    DirectoryCreate,
    DirectoryResponse,
    DirectoryUpdate,
    SourceCreate,
    SourceResponse,
    SourceUpdate,
)
from assistant.blogs.service import (
    SourceChanges,
    create_directory,
    delete_directory,
    delete_source,
    get_source,
    list_directories,
    list_sources,
    register_source,
    rename_directory,
    update_source,
    useful_post_count,
)

router = APIRouter()


# --- Directories ---


@router.get("/directory", response_model=list[DirectoryResponse])
def list_directories_endpoint(
    session: SessionDep, user: CurrentUser
) -> list[DirectoryResponse]:
    return [DirectoryResponse.model_validate(d) for d in list_directories(session, user)]


@router.post("/directory", status_code=201, response_model=DirectoryResponse)
def create_directory_endpoint(
    body: DirectoryCreate, session: SessionDep, user: CurrentUser
) -> DirectoryResponse:
    return DirectoryResponse.model_validate(create_directory(session, user, body.name))


@router.patch("/directory/{directory_id}", response_model=DirectoryResponse)
def rename_directory_endpoint(
    directory_id: uuid.UUID,
    body: DirectoryUpdate,
    session: SessionDep,
    user: CurrentUser,
) -> DirectoryResponse:
    directory = rename_directory(session, user, directory_id, body.name)
    return DirectoryResponse.model_validate(directory)


@router.delete("/directory/{directory_id}", status_code=204)
def delete_directory_endpoint(
    directory_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> None:
    delete_directory(session, user, directory_id)


# --- Sources ---


@router.get("/source", response_model=list[SourceResponse])
def list_sources_endpoint(
    session: SessionDep,
    user: CurrentUser,
    archived: Annotated[bool, Query()] = False,
) -> list[SourceResponse]:
    """List active sources, or with `archived` those with useful posts left."""
    sources = list_sources(session, user, archived=archived)
    return [SourceResponse.model_validate(s) for s in sources]


@router.post("/source", status_code=201, response_model=SourceResponse)
def register_source_endpoint(
    body: SourceCreate, session: SessionDep, user: CurrentUser
) -> SourceResponse:
    """Resolve the URL (feed, advertised feed, sitemap) and register it."""
    source = register_source(
        session,
        user,
        body.url,
        title=body.title,
        remarks=body.remarks,
        preferences=body.preferences,
        directory_id=body.directory_id,
        lookback_days=body.lookback_days,
    )
    return SourceResponse.model_validate(source)


@router.get("/source/{source_id}", response_model=SourceResponse)
def get_source_endpoint(
    source_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> SourceResponse:
    source = get_source(session, user, source_id)
    return SourceResponse.model_validate(source).model_copy(
        update={"useful_post_count": useful_post_count(session, source.id)},
    )


@router.patch("/source/{source_id}", response_model=SourceResponse)
def update_source_endpoint(
    source_id: uuid.UUID,
    body: SourceUpdate,
    session: SessionDep,
    user: CurrentUser,
) -> SourceResponse:
    """Edit, pause or move a source."""
    changes = cast("SourceChanges", body.model_dump(exclude_unset=True))
    return SourceResponse.model_validate(update_source(session, user, source_id, changes))


@router.delete("/source/{source_id}", status_code=204)
def delete_source_endpoint(
    source_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
    keep_useful: Annotated[bool, Query()] = False,
) -> None:
    """Delete a source and all its posts, or with `keep_useful` archive it."""
    delete_source(session, user, source_id, keep_useful=keep_useful)
