from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


Role = Literal["system", "user", "assistant", "tool"]


class ApiModel(BaseModel):
    model_config = ConfigDict(protected_namespaces=())


class MessageInput(ApiModel):
    role: Role
    content: str


class MessageRecord(ApiModel):
    id: str
    chat_id: str
    role: Role
    content: str
    model_id: str | None = None
    created_at: datetime


class ChatSummary(ApiModel):
    id: str
    title: str
    selected_model_id: str | None = None
    created_at: datetime
    updated_at: datetime


class ChatDetail(ChatSummary):
    messages: list[MessageRecord] = Field(default_factory=list)


class CreateChatRequest(ApiModel):
    title: str | None = None
    selected_model_id: str | None = None


class UpdateChatRequest(ApiModel):
    title: str | None = None
    selected_model_id: str | None = None


class ModelDescriptor(ApiModel):
    id: str
    display_name: str
    quantization: str
    tier: str
    description: str


class ModelsResponse(ApiModel):
    default_model_id: str
    models: list[ModelDescriptor]


class ModelSelectionRequest(ApiModel):
    model_id: str


class ModelSelectionResponse(ApiModel):
    model_id: str


class ChatCompletionRequest(ApiModel):
    model: str | None = None
    messages: list[MessageInput]
    stream: bool = True
    chat_id: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=4096)


class ChatCompletionChoice(ApiModel):
    index: int = 0
    message: MessageInput
    finish_reason: str = "stop"


class ChatCompletionUsage(ApiModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class ChatCompletionResponse(ApiModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatCompletionChoice]
    usage: ChatCompletionUsage = Field(default_factory=ChatCompletionUsage)
    metadata: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(ApiModel):
    status: str
    version: str
    ollama_reachable: bool
