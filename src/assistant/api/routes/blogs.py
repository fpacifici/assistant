"""Blog API routes.

Everything but HTTP work is in `assistant.blogs.service`, and for the
collection log in `assistant.blogs.runs`.
"""

from __future__ import annotations

import uuid
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query, Request

from assistant.api.dependencies import CurrentUser, SessionDep
from assistant.api.schemas.blogs import (
    BulkPostStateResponse,
    BulkPostStateUpdate,
    CollectionRunDetailResponse,
    CollectionRunResponse,
    DirectoryCreate,
    DirectoryResponse,
    DirectoryUpdate,
    PostListResponse,
    PostReadUpdate,
    PostResponse,
    PostStateUpdate,
    SourceCreate,
    SourceResponse,
    SourceUpdate,
)
from assistant.api.schemas.tags import NoteTagAdd, TagResponse
from assistant.blogs.refresh import BlogRefresher
from assistant.blogs.runs import get_run, list_runs, refreshable_source, verdict_counts
from assistant.blogs.service import (
    PostFilters,
    PostView,
    SourceChanges,
    add_tag_to_post,
    create_directory,
    delete_directory,
    delete_source,
    get_source,
    list_directories,
    list_posts,
    list_sources,
    register_source,
    remove_tag_from_post,
    rename_directory,
    set_post_read,
    set_post_state,
    set_posts_state,
    tags_for_posts,
    update_source,
    useful_post_count,
)
from assistant.chat.exceptions import AIDisabledError
from assistant.models.schema import BlogPost, Tag

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


# --- Collection log ---


def get_blog_refresher(request: Request) -> BlogRefresher:
    """The app's refresher; 503 (`AIDisabledError`) when AI is disabled."""
    refresher: BlogRefresher | None = request.app.state.blog_refresher
    if refresher is None:
        raise AIDisabledError
    return refresher


BlogRefresherDep = Annotated[BlogRefresher, Depends(get_blog_refresher)]


@router.get("/source/{source_id}/run", response_model=list[CollectionRunResponse])
def list_runs_endpoint(
    source_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> list[CollectionRunResponse]:
    """The latest collection runs of a source, newest first."""
    runs = list_runs(session, user, source_id)
    counts = verdict_counts(session, [run.id for run in runs])
    return [
        CollectionRunResponse.model_validate(run).model_copy(
            update={"verdicts": counts[run.id]}
        )
        for run in runs
    ]


@router.get(
    "/source/{source_id}/run/{run_id}", response_model=CollectionRunDetailResponse
)
def get_run_endpoint(
    source_id: uuid.UUID, run_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> CollectionRunDetailResponse:
    """A run with every logged entry and what the analysis did."""
    run = get_run(session, user, source_id, run_id)
    return CollectionRunDetailResponse.model_validate(run).model_copy(
        update={"verdicts": verdict_counts(session, [run.id])[run.id]}
    )


@router.post(
    "/source/{source_id}/refresh",
    status_code=202,
    response_model=CollectionRunResponse,
)
def refresh_source_endpoint(
    source_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
    refresher: BlogRefresherDep,
) -> CollectionRunResponse:
    """Collect a source now, in the background. Follow the run it returns.

    409 while the job or another refresh is running, or if the source is paused.
    """
    source = refreshable_source(session, user, source_id)
    run_id = refresher.start(source.id)
    return CollectionRunResponse.model_validate(get_run(session, user, source.id, run_id))


# --- Posts ---


def _post_response(post: BlogPost, tags: list[Tag]) -> PostResponse:
    return PostResponse(
        id=post.id,
        source_id=post.source_id,
        source_title=post.source.title,
        url=post.url,
        title=post.title,
        published_at=post.published_at,
        summary=post.summary,
        match_level=post.match_level,
        motivation=post.motivation,
        status=post.status,
        state=post.state,
        evaluated_at=post.evaluated_at,
        read_at=post.read_at,
        tags=[TagResponse.model_validate(tag) for tag in tags],
    )


@router.get("/post", response_model=PostListResponse)
def list_posts_endpoint(  # noqa: PLR0913
    session: SessionDep,
    user: CurrentUser,
    view: Annotated[PostView, Query()] = PostView.ALL,
    directory_id: Annotated[uuid.UUID | None, Query()] = None,
    unfiled: Annotated[bool, Query()] = False,
    source_id: Annotated[uuid.UUID | None, Query()] = None,
    tag: Annotated[uuid.UUID | None, Query()] = None,
    read: Annotated[bool | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PostListResponse:
    """List posts. Pass `next_cursor` back as `cursor` for the next page."""
    page = list_posts(
        session,
        user,
        view=view,
        filters=PostFilters(
            directory_id=directory_id,
            unfiled=unfiled,
            source_id=source_id,
            tag_id=tag,
            read=read,
        ),
        cursor=cursor,
        limit=limit,
    )
    return PostListResponse(
        posts=[_post_response(p, page.tags.get(p.id, [])) for p in page.posts],
        next_cursor=page.next_cursor,
    )


@router.post("/post/bulk-state", response_model=BulkPostStateResponse)
def bulk_post_state_endpoint(
    body: BulkPostStateUpdate, session: SessionDep, user: CurrentUser
) -> BulkPostStateResponse:
    """Set the verdict of the listed posts: the ones the user has on screen."""
    updated = set_posts_state(session, user, body.post_ids, body.state)
    return BulkPostStateResponse(updated=updated)


@router.patch("/post/{post_id}", response_model=PostResponse)
def set_post_state_endpoint(
    post_id: uuid.UUID,
    body: PostStateUpdate,
    session: SessionDep,
    user: CurrentUser,
) -> PostResponse:
    """Set a post's verdict. Undo sets it back."""
    post = set_post_state(session, user, post_id, body.state)
    return _post_response(post, tags_for_posts(session, [post.id]).get(post.id, []))


@router.put("/post/{post_id}/read", response_model=PostResponse)
def set_post_read_endpoint(
    post_id: uuid.UUID,
    body: PostReadUpdate,
    session: SessionDep,
    user: CurrentUser,
) -> PostResponse:
    """Mark a post read, or back to read later. The verdict is unchanged."""
    post = set_post_read(session, user, post_id, read=body.read)
    return _post_response(post, tags_for_posts(session, [post.id]).get(post.id, []))


@router.post("/post/{post_id}/tag", response_model=list[TagResponse])
def add_post_tag_endpoint(
    post_id: uuid.UUID,
    body: NoteTagAdd,
    session: SessionDep,
    user: CurrentUser,
) -> list[TagResponse]:
    """Tag a post by id, or by name (creating the tag if needed).

    Returns the post's tags after the change.
    """
    add_tag_to_post(session, user, post_id, tag_id=body.tag_id, name=body.name)
    tags = tags_for_posts(session, [post_id]).get(post_id, [])
    return [TagResponse.model_validate(tag) for tag in tags]


@router.delete("/post/{post_id}/tag/{tag_id}", status_code=204)
def remove_post_tag_endpoint(
    post_id: uuid.UUID,
    tag_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
) -> None:
    remove_tag_from_post(session, user, post_id, tag_id)
