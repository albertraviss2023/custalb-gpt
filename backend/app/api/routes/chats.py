from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_model_registry, get_repository
from app.core.auth import require_api_key
from app.db.repository import Repository
from app.models.schemas import ChatDetail, ChatSummary, CreateChatRequest, UpdateChatRequest
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

    title = payload.title or f"New Chat {datetime.now(UTC).strftime('%Y-%m-%d %H:%M')}"
    return repository.create_chat(title=title, selected_model_id=payload.selected_model_id)


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