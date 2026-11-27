"""Presence and live note routes.

An open note beats (`PUT .../presence/{client_id}`) every 10 seconds and on
cursor moves, and polls `GET .../live` for other people's edits and cursors.
The note list polls `GET /notebook/{id}/presence`. See
`assistant.notes.presence`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response

from assistant.api.dependencies import CurrentUser, SessionDep
from assistant.api.schemas.presence import (
    HeartbeatRequest,
    LiveNoteResponse,
    NotePresenceResponse,
)
from assistant.notes.presence import (
    Cursor,
    active_in_notebook,
    heartbeat,
    leave,
    live_state,
)
from assistant.notes.service import validate_note_in_notebook

router = APIRouter()


@router.put(
    "/{notebook_id}/note/{note_id}/presence/{client_id}",
    status_code=204,
)
def heartbeat_endpoint(  # noqa: PLR0913
    notebook_id: uuid.UUID,
    note_id: uuid.UUID,
    client_id: uuid.UUID,
    body: HeartbeatRequest,
    session: SessionDep,
    user: CurrentUser,
) -> Response:
    """Mark the caller's tab as having the note open, with its cursor."""
    validate_note_in_notebook(session, notebook_id, note_id)
    cursor = Cursor(body.cursor.node_id, body.cursor.offset) if body.cursor else None
    heartbeat(session, note_id, user, client_id, cursor)
    return Response(status_code=204)


@router.delete(
    "/{notebook_id}/note/{note_id}/presence/{client_id}",
    status_code=204,
)
def leave_endpoint(
    notebook_id: uuid.UUID,  # noqa: ARG001 - part of the note's URL only
    note_id: uuid.UUID,
    client_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
) -> Response:
    """Forget the caller's tab on the note. Idempotent."""
    leave(session, note_id, user, client_id)
    return Response(status_code=204)


@router.get(
    "/{notebook_id}/note/{note_id}/live",
    response_model=LiveNoteResponse,
)
def live_note_endpoint(
    notebook_id: uuid.UUID,
    note_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
    since: str | None = None,
) -> LiveNoteResponse:
    """The note's revision, its nodes when it changed since `since`, and who is on it."""
    validate_note_in_notebook(session, notebook_id, note_id)
    return LiveNoteResponse.model_validate(live_state(session, note_id, user, since))


@router.get(
    "/{notebook_id}/presence",
    response_model=list[NotePresenceResponse],
)
def notebook_presence_endpoint(
    notebook_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
) -> list[NotePresenceResponse]:
    """Who else is on each note of the notebook the caller can view."""
    entries = active_in_notebook(session, notebook_id, user)
    return [NotePresenceResponse.model_validate(e) for e in entries]
