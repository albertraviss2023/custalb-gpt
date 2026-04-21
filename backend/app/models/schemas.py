from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


Role = Literal["system", "user", "assistant", "tool"]
ThinkingLevel = Literal["fast", "balanced", "deep"]
ResponseLength = Literal["concise", "standard", "detailed"]


class ApiModel(BaseModel):
    model_config = ConfigDict(protected_namespaces=())


class ContentPart(ApiModel):
    type: Literal["text", "image_url"]
    text: str | None = None
    image_url: dict[str, str] | None = None


class MessageInput(ApiModel):
    role: Role
    content: str | list[ContentPart]


class InterviewPanelMemberInput(ApiModel):
    name: str
    title: str
    nationality: str | None = None
    voice_id: str | None = None
    gender: Literal["female", "male", "unknown"] | None = None
    accent: Literal["auto", "en-gb", "en-us", "en-au", "en-in", "en-za"] | None = None
    tone: Literal["formal", "probing", "neutral", "supportive", "skeptical"] | None = "neutral"
    speaking_style: Literal["fast", "structured", "conversational", "strict"] | None = "structured"
    avatar_url: str | None = None


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
    inherit_from_chat_id: str | None = None
    inherit_recent_messages: int = Field(default=12, ge=0, le=100)


class UpdateChatRequest(ApiModel):
    title: str | None = None
    selected_model_id: str | None = None


class ModelDescriptor(ApiModel):
    id: str
    display_name: str
    quantization: str
    tier: str
    description: str
    runtime_ref: str | None = None
    available: bool = True


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
    thinking_level: ThinkingLevel = "balanced"
    response_length: ResponseLength = "concise"
    addon_id: str | None = None
    attachment_upload_ids: list[str] = Field(default_factory=list)
    web_mode: bool = False
    interview_role: str | None = None
    interview_panel_members: int | None = Field(default=None, ge=1, le=5)
    interview_organization_type: Literal["un", "private_sector"] | None = None
    interview_organization_name: str | None = None
    interview_location: str | None = None
    interview_is_hq: bool | None = None
    interview_panelists: list[InterviewPanelMemberInput] = Field(default_factory=list)
    interview_difficulty: Literal["medium", "high"] | None = None
    interview_realism_intensity: Literal["low", "medium", "high", "extreme"] | None = "medium"
    interview_role_level: Literal["P2", "P3", "P4", "P5", "D1", "D2"] | None = "P3"
    interview_duration_minutes: int | None = Field(default=None, ge=5, le=180)
    delivery_signals: dict[str, Any] = Field(default_factory=dict)
    regenerate_target_message_id: str | None = None


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
    runtime_reachable: bool
    tts_reachable: bool | None = None


class TtsSynthesisRequest(ApiModel):
    text: str = Field(min_length=1, max_length=3000)
    speaker_name: str | None = None
    voice_id: str | None = None
    accent: str | None = None
    tone: str | None = None
    speaking_style: str | None = None


class AddonDescriptor(ApiModel):
    id: str
    name: str
    tagline: str
    description: str
    category: str
    capabilities: list[str] = Field(default_factory=list)
    installed: bool = False


class AddonCatalogResponse(ApiModel):
    addons: list[AddonDescriptor]


class AddonInstallRequest(ApiModel):
    addon_id: str


class AddonInstallResponse(ApiModel):
    addon_id: str
    installed: bool
    installed_at: datetime | None = None


class UploadStartRequest(ApiModel):
    filename: str
    total_size_bytes: int = Field(ge=1, le=500 * 1024 * 1024 * 1024)
    mime_type: str | None = None


class UploadRecord(ApiModel):
    id: str
    original_name: str
    mime_type: str | None = None
    total_size_bytes: int
    received_bytes: int
    status: str
    created_at: datetime
    updated_at: datetime


class UploadStartResponse(ApiModel):
    upload_id: str
    max_upload_size_bytes: int
    chunk_endpoint: str
    record: UploadRecord


class UploadChunkResponse(ApiModel):
    upload_id: str
    received_bytes: int
    total_size_bytes: int
    status: str


class LogEventCreate(ApiModel):
    level: Literal["debug", "info", "warning", "error"]
    source: str
    message: str
    chat_id: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class LogEventRecord(ApiModel):
    id: str
    level: str
    source: str
    message: str
    chat_id: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ChatTelemetryResponse(ApiModel):
    chat_id: str
    model_id: str
    context_ceiling_tokens: int
    active_tokens_estimate: int
    pressure_status: Literal["green", "yellow", "red", "unknown"]
    trigger_ratio: float
    trigger_tokens: int
    compaction_count: int
    summary_version: int
    last_compacted_message_id: str | None = None
    recent_events: list[LogEventRecord] = Field(default_factory=list)


class ChatMemoryCompactionRequest(ApiModel):
    forget_message_ids: list[str] = Field(default_factory=list)


class ChatMemoryCompactionResponse(ApiModel):
    chat_id: str
    forgotten_messages: int
    summary_version: int
    compaction_count: int
    token_estimate: int
