"""File upload and download API routes."""

from __future__ import annotations

import uuid
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from assistant.api.dependencies import CurrentUserId, SessionDep, StorageDep
from assistant.api.schemas.files import FileCreate, FileResponse
from assistant.attachments.exceptions import (
    AttachmentNotFoundError,
    FileAccessDeniedError,
    FileExpiredError,
    FileStateError,
)
from assistant.attachments.service import (
    complete_file,
    create_file,
    delete_file_record,
    get_file_bytes,
    upload_chunk,
)
from assistant.models.schema import File, Note

router = APIRouter()


def _handle_attachment_errors(exc: Exception) -> None:
    if isinstance(exc, AttachmentNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, FileAccessDeniedError):
        raise HTTPException(status_code=404, detail="File not found") from exc
    if isinstance(exc, FileExpiredError):
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    if isinstance(exc, FileStateError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/files", status_code=201, response_model=FileResponse)
def create_file_endpoint(
    body: FileCreate,
    session: SessionDep,
    user_id: CurrentUserId,
) -> FileResponse:
    """Initialize a chunked file upload associated with a note."""
    try:
        file = create_file(session, body.note_id, body.file_name, user_id)
    except FileAccessDeniedError as exc:
        raise HTTPException(status_code=404, detail="Note not found") from exc
    return FileResponse.model_validate(file)


@router.put("/files/{file_id}/parts/{part_number}", status_code=204)
async def upload_chunk_endpoint(  # noqa: PLR0913
    file_id: uuid.UUID,
    part_number: int,
    request: Request,
    session: SessionDep,
    storage: StorageDep,
    user_id: CurrentUserId,
) -> Response:
    """Upload one chunk of a file (raw bytes body)."""
    data = await request.body()
    try:
        upload_chunk(session, storage, file_id, part_number, data, user_id)
    except Exception as exc:
        _handle_attachment_errors(exc)
        raise
    return Response(status_code=204)


@router.patch("/files/{file_id}", response_model=FileResponse)
def complete_file_endpoint(
    file_id: uuid.UUID,
    session: SessionDep,
    storage: StorageDep,
    user_id: CurrentUserId,
) -> FileResponse:
    """Complete a chunked upload by merging all parts."""
    try:
        file = complete_file(session, storage, file_id, user_id)
    except Exception as exc:
        _handle_attachment_errors(exc)
        raise
    return FileResponse.model_validate(file)


@router.get("/files/{file_id}")
def download_file_endpoint(
    file_id: uuid.UUID,
    session: SessionDep,
    storage: StorageDep,
    user_id: CurrentUserId,
) -> StreamingResponse:
    """Download a complete file."""
    try:
        file, data = get_file_bytes(session, storage, file_id, user_id)
    except Exception as exc:
        _handle_attachment_errors(exc)
        raise
    encoded_name = quote(file.file_name, safe="")
    content_disposition = f"attachment; filename*=UTF-8''{encoded_name}"
    return StreamingResponse(
        iter([data]),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": content_disposition,
            "Content-Length": str(len(data)),
        },
    )


@router.delete("/files/{file_id}", status_code=204)
def delete_file_endpoint(
    file_id: uuid.UUID,
    session: SessionDep,
    storage: StorageDep,
    user_id: CurrentUserId,
) -> Response:
    """Delete a file and its physical data. Idempotent."""
    file = session.get(File, file_id)
    if file is not None:
        note = session.get(Note, file.note_id)
        if note is None or note.owner_id != user_id:
            raise HTTPException(status_code=404, detail="File not found")
    delete_file_record(session, storage, file_id)
    return Response(status_code=204)
