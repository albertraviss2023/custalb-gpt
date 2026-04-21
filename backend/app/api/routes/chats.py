from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_chat_service, get_model_registry, get_repository
from app.core.auth import require_api_key
from app.db.repository import Repository
from app.models.schemas import (
    ChatDetail,
    ChatMemoryCompactionRequest,
    ChatMemoryCompactionResponse,
    ChatSummary,
    CreateChatRequest,
    UpdateChatRequest,
)
from app.services.chat_service import ChatService
from app.services.model_registry import ModelRegistry

router = APIRouter(prefix="/v1/chats", tags=["chats"], dependencies=[Depends(require_api_key)])


@router.get("", response_model=list[ChatSummary])
def list_chats(repository: Repository = Depends(get_repository)) -> list[ChatSummary]:
    return repository.list_chats()


@router.post("", response_model=ChatSummary, status_code=status.HTTP_201_CREATED)
def create_chat(
    payload: CreateChatRequest,
    repository: Repository = Depends(get_repository),
    model_registry: ModelRegistry = Depends(get_model_registry),
) -> ChatSummary:
    if payload.selected_model_id and not model_registry.exists(payload.selected_model_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown model id")
    if payload.inherit_from_chat_id and not repository.get_chat(payload.inherit_from_chat_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source chat not found")

    title = payload.title or f"New Chat {datetime.now(UTC).strftime('%Y-%m-%d %H:%M')}"
    selected_model_id = payload.selected_model_id or model_registry.default_model_id
    if payload.inherit_from_chat_id:
        return repository.create_chat_with_inheritance(
            title=title,
            selected_model_id=selected_model_id,
            source_chat_id=payload.inherit_from_chat_id,
            inherit_recent_messages=payload.inherit_recent_messages,
        )
    return repository.create_chat(title=title, selected_model_id=selected_model_id)


@router.get("/{chat_id}", response_model=ChatDetail)
def get_chat(chat_id: str, repository: Repository = Depends(get_repository)) -> ChatDetail:
    chat = repository.get_chat(chat_id)
    if not chat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    return chat


@router.patch("/{chat_id}", response_model=ChatSummary)
def update_chat(
    chat_id: str,
    payload: UpdateChatRequest,
    repository: Repository = Depends(get_repository),
    model_registry: ModelRegistry = Depends(get_model_registry),
) -> ChatSummary:
    if payload.selected_model_id is not None and not model_registry.exists(payload.selected_model_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown model id")

    updated = repository.update_chat(
        chat_id=chat_id,
        title=payload.title,
        selected_model_id=payload.selected_model_id,
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    return updated


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat(chat_id: str, repository: Repository = Depends(get_repository)) -> None:
    deleted = repository.delete_chat(chat_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")


@router.post("/{chat_id}/memory/compact", response_model=ChatMemoryCompactionResponse)
def compact_chat_memory(
    chat_id: str,
    payload: ChatMemoryCompactionRequest,
    chat_service: ChatService = Depends(get_chat_service),
) -> ChatMemoryCompactionResponse:
    result = chat_service.manual_compact_chat_context(
        chat_id=chat_id,
        forget_message_ids=payload.forget_message_ids,
    )
    return ChatMemoryCompactionResponse(
        chat_id=chat_id,
        forgotten_messages=int(result["forgotten_messages"]),
        summary_version=int(result["summary_version"]),
        compaction_count=int(result["compaction_count"]),
        token_estimate=int(result["token_estimate"]),
    )
