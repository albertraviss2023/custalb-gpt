from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_model_registry, get_repository
from app.core.auth import require_api_key
from app.db.repository import Repository
from app.models.schemas import ChatTelemetryResponse
from app.services.chat_service import COMPACTION_TRIGGER_RATIO, STATIC_CONTEXT_CEILING
from app.services.model_registry import ModelRegistry

router = APIRouter(prefix="/v1/chats", tags=["telemetry"], dependencies=[Depends(require_api_key)])


def _estimate_tokens(text: str) -> int:
    cleaned = text.strip()
    if not cleaned:
        return 0
    return max(1, (len(cleaned) + 3) // 4)


def _pressure(active: int, ceiling: int) -> str:
    if ceiling <= 0:
        return "unknown"
    ratio = active / ceiling
    if ratio < 0.75:
        return "green"
    if ratio < 0.9:
        return "yellow"
    return "red"


@router.get("/{chat_id}/telemetry", response_model=ChatTelemetryResponse)
def get_chat_telemetry(
    chat_id: str,
    repository: Repository = Depends(get_repository),
    model_registry: ModelRegistry = Depends(get_model_registry),
) -> ChatTelemetryResponse:
    chat = repository.get_chat(chat_id)
    if not chat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")

    model_id = chat.selected_model_id or model_registry.default_model_id
    if not model_registry.exists(model_id):
        model_id = model_registry.default_model_id
    profile = model_registry.get(model_id)
    ceiling = max(256, min(profile.limits.max_context_tokens, STATIC_CONTEXT_CEILING))
    trigger_tokens = int(ceiling * COMPACTION_TRIGGER_RATIO)

    memory = repository.get_chat_memory(chat_id)
    if memory:
        active_estimate = int(memory.get("token_estimate", 0))
        compaction_count = int(memory.get("compaction_count", 0))
        summary_version = int(memory.get("summary_version", 0))
        last_compacted_message_id = memory.get("last_compacted_message_id")
    else:
        active_estimate = sum(_estimate_tokens(message.content) for message in chat.messages)
        compaction_count = 0
        summary_version = 0
        last_compacted_message_id = None

    events = [
        event for event in repository.list_log_events(limit=200)
        if event.chat_id == chat_id and event.source == "context_compactor"
    ][:20]

    return ChatTelemetryResponse(
        chat_id=chat_id,
        model_id=model_id,
        context_ceiling_tokens=ceiling,
        active_tokens_estimate=active_estimate,
        pressure_status=_pressure(active_estimate, ceiling),
        trigger_ratio=COMPACTION_TRIGGER_RATIO,
        trigger_tokens=trigger_tokens,
        compaction_count=compaction_count,
        summary_version=summary_version,
        last_compacted_message_id=last_compacted_message_id,
        recent_events=events,
    )

