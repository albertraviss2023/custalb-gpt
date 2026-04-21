from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_repository
from app.core.auth import require_api_key
from app.db.repository import Repository
from app.models.schemas import LogEventCreate, LogEventRecord

router = APIRouter(prefix="/v1/logs", tags=["logs"], dependencies=[Depends(require_api_key)])


@router.post("/events", response_model=LogEventRecord)
def create_log_event(
    payload: LogEventCreate,
    repository: Repository = Depends(get_repository),
) -> LogEventRecord:
    return repository.add_log_event(
        level=payload.level,
        source=payload.source,
        message=payload.message,
        context=payload.context,
        chat_id=payload.chat_id,
    )


@router.get("/events", response_model=list[LogEventRecord])
def list_log_events(
    limit: int = Query(default=100, ge=1, le=500),
    repository: Repository = Depends(get_repository),
) -> list[LogEventRecord]:
    return repository.list_log_events(limit=limit)
