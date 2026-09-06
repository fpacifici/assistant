"""Notebook API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response

from assistant.api.dependencies import CurrentUser, SessionDep
from assistant.api.routes._sharing import validate_role_for_subject_type
from assistant.api.schemas.notebooks import (
    EntitlementCreate,
    EntitlementResponse,
    NotebookCreate,
    NotebookResponse,
    NotebookUpdate,
)
from assistant.api.schemas.pagination import Pagination
from assistant.models.schema import Notebook, SubjectType, User
from assistant.notes.entitlements import (
    grant_entitlement,
    list_entitlements,
    revoke_entitlement,
)
from assistant.notes.permissions import notebook_permissions
from assistant.notes.service import (
    create_notebook,
    delete_notebook,
    get_notebook,
    list_notebooks,
    update_notebook,
)

router = APIRouter()


def _notebook_response(
    session: SessionDep,
    notebook: Notebook,
    caller: User,
) -> NotebookResponse:
    perms = notebook_permissions(session, caller, notebook.id)
    return NotebookResponse(
        id=notebook.id,
        name=notebook.name,
        owner_id=notebook.owner_id,
        permissions=sorted(perms, key=lambda p: p.value),
    )


@router.post("", status_code=201, response_model=NotebookResponse)
def create_notebook_endpoint(
    body: NotebookCreate,
    session: SessionDep,
    user: CurrentUser,
) -> NotebookResponse:
    notebook = create_notebook(session, name=body.name, owner=user)
    return _notebook_response(session, notebook, user)


@router.get("", response_model=list[NotebookResponse])
def list_notebooks_endpoint(
    session: SessionDep,
    user: CurrentUser,
    pagination: Pagination,
) -> list[NotebookResponse]:
    notebooks = list_notebooks(
        session,
        user,
        offset=pagination.offset,
        limit=pagination.limit,
    )
    return [_notebook_response(session, nb, user) for nb in notebooks]


@router.get("/{notebook_id}", response_model=NotebookResponse)
def get_notebook_endpoint(
    notebook_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
) -> NotebookResponse:
    notebook = get_notebook(session, notebook_id, caller=user)
    return _notebook_response(session, notebook, user)


@router.patch("/{notebook_id}", response_model=NotebookResponse)
def update_notebook_endpoint(
    notebook_id: uuid.UUID,
    body: NotebookUpdate,
    session: SessionDep,
    user: CurrentUser,
) -> NotebookResponse:
    notebook = update_notebook(session, notebook_id, caller=user, name=body.name)
    return _notebook_response(session, notebook, user)


@router.delete("/{notebook_id}", status_code=204)
def delete_notebook_endpoint(
    notebook_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
) -> Response:
    delete_notebook(session, notebook_id, caller=user)
    return Response(status_code=204)


@router.post("/{notebook_id}/share", status_code=201, response_model=EntitlementResponse)
def share_notebook_endpoint(
    notebook_id: uuid.UUID,
    body: EntitlementCreate,
    session: SessionDep,
    user: CurrentUser,
) -> EntitlementResponse:
    validate_role_for_subject_type(body.role, SubjectType.NOTEBOOK)
    entitlement = grant_entitlement(
        session,
        user,
        notebook_id=notebook_id,
        grantee_email=body.email,
        role_name=body.role,
    )
    return EntitlementResponse.from_entitlement(entitlement)


@router.get("/{notebook_id}/share", response_model=list[EntitlementResponse])
def list_notebook_shares_endpoint(
    notebook_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
) -> list[EntitlementResponse]:
    entitlements = list_entitlements(session, user, notebook_id=notebook_id)
    return [EntitlementResponse.from_entitlement(e) for e in entitlements]


@router.delete("/{notebook_id}/share/{entitlement_id}", status_code=204)
def revoke_notebook_share_endpoint(
    notebook_id: uuid.UUID,
    entitlement_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
) -> Response:
    revoke_entitlement(session, user, entitlement_id, notebook_id=notebook_id)
    return Response(status_code=204)
