"""Note API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response

from assistant.api.dependencies import CurrentUserId, SessionDep
from assistant.api.schemas.notes import NoteCreate, NoteResponse, NoteUpdate
from assistant.api.schemas.pagination import Pagination
from assistant.models.schema import Note
from assistant.notes.exceptions import NoteNotFoundError
from assistant.notes.service import (
    create_note,
    delete_note,
    get_note,
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
    note = create_note(
        session,
        notebook_id=notebook_id,
        owner_id=user_id,
        title=body.title,
    )
    return NoteResponse.model_validate(note)


@router.get(
    "/{notebook_id}/note",
    response_model=list[NoteResponse],
)
def list_notes_endpoint(
    notebook_id: uuid.UUID,
    session: SessionDep,
    pagination: Pagination,
) -> list[NoteResponse]:
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
) -> NoteResponse:
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
) -> NoteResponse:
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
) -> Response:
    _get_note_in_notebook(session, notebook_id, note_id)
    delete_note(session, note_id)
    return Response(status_code=204)
