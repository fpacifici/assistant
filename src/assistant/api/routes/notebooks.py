"""Notebook API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response

from assistant.api.dependencies import CurrentUserId, SessionDep, require_notebook_owner
from assistant.api.schemas.notebooks import (
    NotebookCreate,
    NotebookResponse,
    NotebookUpdate,
)
from assistant.api.schemas.pagination import Pagination
from assistant.notes.service import (
    create_notebook,
    delete_notebook,
    list_notebooks,
    update_notebook,
)

router = APIRouter()


@router.post("", status_code=201, response_model=NotebookResponse)
def create_notebook_endpoint(
    body: NotebookCreate,
    session: SessionDep,
    user_id: CurrentUserId,
) -> NotebookResponse:
    notebook = create_notebook(session, name=body.name, owner_id=user_id)
    return NotebookResponse.model_validate(notebook)


@router.get("", response_model=list[NotebookResponse])
def list_notebooks_endpoint(
    session: SessionDep,
    user_id: CurrentUserId,
    pagination: Pagination,
) -> list[NotebookResponse]:
    notebooks = list_notebooks(
        session,
        owner_id=user_id,
        offset=pagination.offset,
        limit=pagination.limit,
    )
    return [NotebookResponse.model_validate(nb) for nb in notebooks]


@router.get("/{notebook_id}", response_model=NotebookResponse)
def get_notebook_endpoint(
    notebook_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
) -> NotebookResponse:
    notebook = require_notebook_owner(session, notebook_id, user_id)
    return NotebookResponse.model_validate(notebook)


@router.patch("/{notebook_id}", response_model=NotebookResponse)
def update_notebook_endpoint(
    notebook_id: uuid.UUID,
    body: NotebookUpdate,
    session: SessionDep,
    user_id: CurrentUserId,
) -> NotebookResponse:
    require_notebook_owner(session, notebook_id, user_id)
    notebook = update_notebook(session, notebook_id, name=body.name)
    return NotebookResponse.model_validate(notebook)


@router.delete("/{notebook_id}", status_code=204)
def delete_notebook_endpoint(
    notebook_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
) -> Response:
    require_notebook_owner(session, notebook_id, user_id)
    delete_notebook(session, notebook_id)
    return Response(status_code=204)
