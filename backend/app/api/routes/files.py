from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.api.dependencies import get_repository
from app.core.auth import require_api_key
from app.core.settings import settings
from app.db.repository import Repository
from app.models.schemas import (
    UploadChunkResponse,
    UploadRecord,
    UploadStartRequest,
    UploadStartResponse,
)

router = APIRouter(prefix="/v1/files", tags=["files"], dependencies=[Depends(require_api_key)])


def _upload_path(upload_id: str, filename: str) -> Path:
    safe_name = filename.replace("\\", "_").replace("/", "_").strip() or "upload.bin"
    return settings.resolved_uploads_dir() / f"{upload_id}__{safe_name}"


@router.post("/uploads/start", response_model=UploadStartResponse)
def start_upload(
    payload: UploadStartRequest,
    repository: Repository = Depends(get_repository),
) -> UploadStartResponse:
    if payload.total_size_bytes > settings.max_upload_size_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Upload exceeds max size")

    upload_id = str(uuid.uuid4())
    path = _upload_path(upload_id, payload.filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=False)
    record = repository.create_upload(
        upload_id=upload_id,
        original_name=payload.filename,
        mime_type=payload.mime_type,
        total_size_bytes=payload.total_size_bytes,
        storage_path=str(path),
    )
    return UploadStartResponse(
        upload_id=upload_id,
        max_upload_size_bytes=settings.max_upload_size_bytes,
        chunk_endpoint=f"/v1/files/uploads/{upload_id}/chunk",
        record=record,
    )


@router.put("/uploads/{upload_id}/chunk", response_model=UploadChunkResponse)
async def upload_chunk(
    upload_id: str,
    request: Request,
    repository: Repository = Depends(get_repository),
    x_upload_offset: int = Header(alias="X-Upload-Offset"),
    x_upload_complete: str | None = Header(default=None, alias="X-Upload-Complete"),
) -> UploadChunkResponse:
    record = repository.get_upload(upload_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload session not found")
    if record.status == "completed":
        return UploadChunkResponse(
            upload_id=upload_id,
            received_bytes=record.received_bytes,
            total_size_bytes=record.total_size_bytes,
            status=record.status,
        )

    if x_upload_offset != record.received_bytes:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invalid chunk offset")

    storage = repository.get_upload_storage_path(upload_id)
    if not storage:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Upload path not found")

    chunk_size = 0
    with Path(storage).open("ab") as handle:
        async for block in request.stream():
            if not block:
                continue
            chunk_size += len(block)
            handle.write(block)

    new_total = record.received_bytes + chunk_size
    if new_total > record.total_size_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Chunk exceeds declared total size")

    complete_flag = (x_upload_complete or "").lower() in {"1", "true", "yes"}
    status_value = "completed" if complete_flag or new_total == record.total_size_bytes else "uploading"
    updated = repository.update_upload_progress(upload_id, received_bytes=new_total, status=status_value)
    if not updated:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update upload")

    return UploadChunkResponse(
        upload_id=upload_id,
        received_bytes=updated.received_bytes,
        total_size_bytes=updated.total_size_bytes,
        status=updated.status,
    )


@router.get("/uploads", response_model=list[UploadRecord])
def list_uploads(repository: Repository = Depends(get_repository)) -> list[UploadRecord]:
    return repository.list_uploads()


@router.delete("/uploads/{upload_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_upload(upload_id: str, repository: Repository = Depends(get_repository)) -> None:
    storage_path = repository.delete_upload(upload_id)
    if not storage_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")
    path = Path(storage_path)
    try:
        if path.exists():
            path.unlink()
    except OSError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete file: {exc}") from exc
