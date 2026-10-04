"""Notes-import API routes: upload an Evernote HTML export zip, then run it."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from assistant.adapters.zip_import import (
    ImportNotFoundError,
    InvalidImportArchiveError,
    UploadTooLargeError,
    import_zip,
    store_upload,
)
from assistant.api.dependencies import CurrentUser, ImportSettingsDep, SessionDep
from assistant.api.schemas.imports import (
    ImportReportResponse,
    ImportRunRequest,
    ImportUploadResponse,
)

router = APIRouter()

# Allowance for the multipart envelope around the file itself.
_MULTIPART_OVERHEAD_BYTES = 64 * 1024


@router.post("", status_code=201, response_model=ImportUploadResponse)
def upload_import_endpoint(
    request: Request,
    file: Annotated[UploadFile, File()],
    user: CurrentUser,
    settings: ImportSettingsDep,
) -> ImportUploadResponse:
    """Store an uploaded zip for a later `POST /imports/{import_id}/run`."""
    content_length = request.headers.get("content-length")
    limit = settings.max_upload_bytes
    if content_length and int(content_length) > limit + _MULTIPART_OVERHEAD_BYTES:
        raise HTTPException(status_code=413, detail=f"Upload exceeds {limit} bytes")
    try:
        import_id = store_upload(
            file.file,
            user,
            storage_root=settings.storage_root,
            max_bytes=limit,
        )
    except UploadTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except InvalidImportArchiveError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ImportUploadResponse(import_id=import_id)


@router.post("/{import_id}/run", response_model=ImportReportResponse)
def run_import_endpoint(
    import_id: uuid.UUID,
    body: ImportRunRequest,
    session: SessionDep,
    user: CurrentUser,
    settings: ImportSettingsDep,
) -> ImportReportResponse:
    """Import a stored upload and return the report. The upload is then deleted."""
    try:
        report = import_zip(
            session,
            import_id,
            user,
            storage_root=settings.storage_root,
            include_web_clips=body.include_web_clips,
        )
    except ImportNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Import not found") from exc
    except InvalidImportArchiveError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ImportReportResponse.model_validate(report)
