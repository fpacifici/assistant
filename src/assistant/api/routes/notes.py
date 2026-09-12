"""Note API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Response

from assistant.api.dependencies import CurrentUser, SessionDep, StorageDep
from assistant.api.routes._sharing import validate_role_for_subject_type
from assistant.api.schemas.notebooks import EntitlementCreate, EntitlementResponse
from assistant.api.schemas.notes import NoteCreate, NoteResponse, NoteUpdate
from assistant.api.schemas.pagination import Pagination
from assistant.attachments.service import delete_file_record
from assistant.models.schema import NodeType, Note, SubjectType, User
from assistant.notes.entitlements import (
    grant_entitlement,
    list_entitlements,
    revoke_entitlement,
    send_share_notification_email,
)
from assistant.notes.exceptions import NoteNotFoundError
from assistant.notes.permissions import note_permissions
from assistant.notes.service import (
    add_text_node,
    create_note,
    delete_note,
    get_note,
    get_ordered_nodes,
    list_notes,
    update_note,
)

router = APIRouter()


def _get_note_in_notebook(
    session: SessionDep,
    notebook_id: uuid.UUID,
    note_id: uuid.UUID,
    caller: User,
) -> Note:
    note = get_note(session, note_id, caller)
    if note.notebook_id != notebook_id:
        raise NoteNotFoundError(str(note_id))
    return note


def _note_response(session: SessionDep, note: Note, caller: User) -> NoteResponse:
    perms = note_permissions(session, caller, note)
    return NoteResponse(
        id=note.id,
        notebook_id=note.notebook_id,
        owner_id=note.owner_id,
        title=note.title,
        creation_timestamp=note.creation_timestamp,
        update_timestamp=note.update_timestamp,
        permissions=sorted(perms, key=lambda p: p.value),
    )


@router.post(
    "/{notebook_id}/note",
    status_code=201,
    response_model=NoteResponse,
)
def create_note_endpoint(
    notebook_id: uuid.UUID,
    body: NoteCreate,
    session: SessionDep,
    user: CurrentUser,
) -> NoteResponse:
    note = create_note(
        session,
        notebook_id=notebook_id,
        owner=user,
        title=body.title,
    )
    add_text_node(session, note_id=note.id, author=user, payload="")
    return _note_response(session, note, user)


@router.get(
    "/{notebook_id}/note",
    response_model=list[NoteResponse],
)
def list_notes_endpoint(
    notebook_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
    pagination: Pagination,
) -> list[NoteResponse]:
    notes = list_notes(
        session,
        notebook_id=notebook_id,
        caller=user,
        offset=pagination.offset,
        limit=pagination.limit,
    )
    return [_note_response(session, n, user) for n in notes]


@router.get(
    "/{notebook_id}/note/{note_id}",
    response_model=NoteResponse,
)
def get_note_endpoint(
    notebook_id: uuid.UUID,
    note_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
) -> NoteResponse:
    note = _get_note_in_notebook(session, notebook_id, note_id, user)
    return _note_response(session, note, user)


@router.patch(
    "/{notebook_id}/note/{note_id}",
    response_model=NoteResponse,
)
def update_note_endpoint(
    notebook_id: uuid.UUID,
    note_id: uuid.UUID,
    body: NoteUpdate,
    session: SessionDep,
    user: CurrentUser,
) -> NoteResponse:
    _get_note_in_notebook(session, notebook_id, note_id, user)
    note = update_note(session, note_id, caller=user, title=body.title)
    return _note_response(session, note, user)


@router.delete(
    "/{notebook_id}/note/{note_id}",
    status_code=204,
)
def delete_note_endpoint(
    notebook_id: uuid.UUID,
    note_id: uuid.UUID,
    session: SessionDep,
    storage: StorageDep,
    user: CurrentUser,
) -> Response:
    _get_note_in_notebook(session, notebook_id, note_id, user)
    nodes = get_ordered_nodes(session, note_id, caller=user)
    file_ids = [
        n.attachment_id
        for n in nodes
        if n.node_type == NodeType.ATTACHMENT and n.attachment_id is not None
    ]
    delete_note(session, note_id, caller=user)
    for file_id in file_ids:
        delete_file_record(session, storage, file_id)
    return Response(status_code=204)


@router.post(
    "/{notebook_id}/note/{note_id}/share",
    status_code=201,
    response_model=EntitlementResponse,
)
def share_note_endpoint(  # noqa: PLR0913
    notebook_id: uuid.UUID,
    note_id: uuid.UUID,
    body: EntitlementCreate,
    session: SessionDep,
    user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> EntitlementResponse:
    _get_note_in_notebook(session, notebook_id, note_id, user)
    validate_role_for_subject_type(body.role, SubjectType.NOTE)
    entitlement, created = grant_entitlement(
        session,
        user,
        note_id=note_id,
        grantee_email=body.email,
        role_name=body.role,
    )
    if created:
        background_tasks.add_task(
            send_share_notification_email,
            granter_name=f"{user.firstname} {user.lastname}",
            grantee_email=body.email,
            role=body.role,
            subject_type=SubjectType.NOTE,
            notebook_id=notebook_id,
            note_id=note_id,
        )
    return EntitlementResponse.from_entitlement(entitlement)


@router.get(
    "/{notebook_id}/note/{note_id}/share",
    response_model=list[EntitlementResponse],
)
def list_note_shares_endpoint(
    notebook_id: uuid.UUID,
    note_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
) -> list[EntitlementResponse]:
    _get_note_in_notebook(session, notebook_id, note_id, user)
    entitlements = list_entitlements(session, user, note_id=note_id)
    return [EntitlementResponse.from_entitlement(e) for e in entitlements]


@router.delete(
    "/{notebook_id}/note/{note_id}/share/{entitlement_id}",
    status_code=204,
)
def revoke_note_share_endpoint(
    notebook_id: uuid.UUID,
    note_id: uuid.UUID,
    entitlement_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
) -> Response:
    _get_note_in_notebook(session, notebook_id, note_id, user)
    revoke_entitlement(session, user, entitlement_id, note_id=note_id)
    return Response(status_code=204)
