"""Note API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response

from assistant.api.dependencies import (
    CurrentUserId,
    SessionDep,
    StorageDep,
    require_notebook_owner,
)
from assistant.api.schemas.notes import NoteCreate, NoteResponse, NoteUpdate
from assistant.api.schemas.pagination import Pagination
from assistant.attachments.service import delete_file_record
from assistant.models.schema import NodeType, Note
from assistant.notes.exceptions import NoteNotFoundError
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
) -> Note:
    note = get_note(session, note_id)
    if note.notebook_id != notebook_id:
        raise NoteNotFoundError(str(note_id))
    return note


@router.post(
    "/{notebook_id}/note",
    status_code=201,
    response_model=NoteResponse,
)
def create_note_endpoint(
    notebook_id: uuid.UUID,
    body: NoteCreate,
    session: SessionDep,
    user_id: CurrentUserId,
) -> NoteResponse:
    require_notebook_owner(session, notebook_id, user_id)
    note = create_note(
        session,
        notebook_id=notebook_id,
        owner_id=user_id,
        title=body.title,
    )
    add_text_node(session, note_id=note.id, author_id=user_id, payload="")
    return NoteResponse.model_validate(note)


@router.get(
    "/{notebook_id}/note",
    response_model=list[NoteResponse],
)
def list_notes_endpoint(
    notebook_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
    pagination: Pagination,
) -> list[NoteResponse]:
    require_notebook_owner(session, notebook_id, user_id)
    notes = list_notes(
        session,
        notebook_id=notebook_id,
        offset=pagination.offset,
        limit=pagination.limit,
    )
    return [NoteResponse.model_validate(n) for n in notes]


@router.get(
    "/{notebook_id}/note/{note_id}",
    response_model=NoteResponse,
)
def get_note_endpoint(
    notebook_id: uuid.UUID,
    note_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
) -> NoteResponse:
    require_notebook_owner(session, notebook_id, user_id)
    note = _get_note_in_notebook(session, notebook_id, note_id)
    return NoteResponse.model_validate(note)


@router.patch(
    "/{notebook_id}/note/{note_id}",
    response_model=NoteResponse,
)
def update_note_endpoint(
    notebook_id: uuid.UUID,
    note_id: uuid.UUID,
    body: NoteUpdate,
    session: SessionDep,
    user_id: CurrentUserId,
) -> NoteResponse:
    require_notebook_owner(session, notebook_id, user_id)
    _get_note_in_notebook(session, notebook_id, note_id)
    note = update_note(session, note_id, title=body.title)
    return NoteResponse.model_validate(note)


@router.delete(
    "/{notebook_id}/note/{note_id}",
    status_code=204,
)
def delete_note_endpoint(
    notebook_id: uuid.UUID,
    note_id: uuid.UUID,
    session: SessionDep,
    storage: StorageDep,
    user_id: CurrentUserId,
) -> Response:
    require_notebook_owner(session, notebook_id, user_id)
    _get_note_in_notebook(session, notebook_id, note_id)
    nodes = get_ordered_nodes(session, note_id)
    file_ids = [
        n.attachment_id
        for n in nodes
        if n.node_type == NodeType.ATTACHMENT and n.attachment_id is not None
    ]
    delete_note(session, note_id)
    for file_id in file_ids:
        delete_file_record(session, storage, file_id)
    return Response(status_code=204)
