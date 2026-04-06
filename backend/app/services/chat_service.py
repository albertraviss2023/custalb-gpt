from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, AsyncIterator

from fastapi import HTTPException, status

from app.db.repository import Repository
from app.models.schemas import ChatCompletionRequest, MessageInput
from app.services.model_registry import ModelRegistry
from app.services.ollama_client import InferenceError, OllamaClient


OOM_MARKERS = ("out of memory", "cuda", "insufficient", "alloc", "oom")


@dataclass(slots=True)
class CompletionResult:
    text: str
    used_model_id: str
    fallback_reason: str | None
    usage: dict[str, int | None]
    attempted_models: list[str]


class ChatService:
    def __init__(
        self,
        *,
        repository: Repository,
        model_registry: ModelRegistry,
        ollama_client: OllamaClient,
    ) -> None:
        self.repository = repository
        self.model_registry = model_registry
        self.ollama_client = ollama_client

    def _resolve_model_id(self, request: ChatCompletionRequest) -> str:
        if request.model:
            if not self.model_registry.exists(request.model):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown model id")
            return request.model

        if request.chat_id:
            chat = self.repository.get_chat(request.chat_id)
            if not chat:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
            if chat.selected_model_id and self.model_registry.exists(chat.selected_model_id):
                return chat.selected_model_id

        stored_default = self.repository.get_default_model_id(self.model_registry.default_model_id)
        if self.model_registry.exists(stored_default):
            return stored_default
        return self.model_registry.default_model_id

    @staticmethod
    def _as_runtime_messages(messages: list[MessageInput]) -> list[dict[str, str]]:
        return [{"role": message.role, "content": message.content} for message in messages]

    @staticmethod
    def _is_fallback_error(error: Exception) -> bool:
        message = str(error).lower()
        if isinstance(error, TimeoutError):
            return True
        return any(marker in message for marker in OOM_MARKERS)

    def _persist_if_needed(self, request: ChatCompletionRequest, assistant_text: str, used_model_id: str) -> None:
        if not request.chat_id:
            return

        chat = self.repository.get_chat(request.chat_id)
        if not chat:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")

        last_user = next((msg for msg in reversed(request.messages) if msg.role == "user"), None)
        if last_user:
            chat_latest = chat.messages[-1] if chat.messages else None
            if not chat_latest or chat_latest.role != "user" or chat_latest.content != last_user.content:
                self.repository.add_message(request.chat_id, "user", last_user.content, None)

        self.repository.add_message(request.chat_id, "assistant", assistant_text, used_model_id)

    async def complete(self, request: ChatCompletionRequest) -> CompletionResult:
        if not request.messages:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="messages cannot be empty")

        requested_model_id = self._resolve_model_id(request)
        chain = self.model_registry.build_fallback_chain(requested_model_id)
        runtime_messages = self._as_runtime_messages(request.messages)

        attempted: list[str] = []
        fallback_reason: str | None = None

        for model_id in chain:
            attempted.append(model_id)
            profile = self.model_registry.get(model_id)

            try:
                response = await self.ollama_client.chat(
                    model_ref=profile.runtime.model_ref,
                    messages=runtime_messages,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                )
                text = str(response.get("message", {}).get("content", "")).strip()
                usage = {
                    "prompt_tokens": response.get("prompt_eval_count"),
                    "completion_tokens": response.get("eval_count"),
                    "total_tokens": (
                        (response.get("prompt_eval_count") or 0) + (response.get("eval_count") or 0)
                    ),
                }
                self._persist_if_needed(request, text, model_id)
                return CompletionResult(
                    text=text,
                    used_model_id=model_id,
                    fallback_reason=fallback_reason,
                    usage=usage,
                    attempted_models=attempted,
                )
            except (InferenceError, TimeoutError) as error:
                if self._is_fallback_error(error):
                    fallback_reason = str(error)
                    continue
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Inference failed: {error}",
                ) from error

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="All model attempts failed",
        )

    async def stream_complete(self, request: ChatCompletionRequest) -> AsyncIterator[dict[str, Any]]:
        if not request.messages:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="messages cannot be empty")

        requested_model_id = self._resolve_model_id(request)
        chain = self.model_registry.build_fallback_chain(requested_model_id)
        runtime_messages = self._as_runtime_messages(request.messages)

        attempted: list[str] = []
        fallback_reason: str | None = None

        for model_id in chain:
            attempted.append(model_id)
            profile = self.model_registry.get(model_id)
            assistant_text = ""
            usage: dict[str, int | None] = {
                "prompt_tokens": None,
                "completion_tokens": None,
                "total_tokens": None,
            }

            try:
                async for chunk in self.ollama_client.stream_chat(
                    model_ref=profile.runtime.model_ref,
                    messages=runtime_messages,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                ):
                    content = str(chunk.get("message", {}).get("content", ""))
                    if content:
                        assistant_text += content
                        yield {
                            "type": "token",
                            "token": content,
                            "used_model_id": model_id,
                        }

                    if chunk.get("done"):
                        usage = {
                            "prompt_tokens": chunk.get("prompt_eval_count"),
                            "completion_tokens": chunk.get("eval_count"),
                            "total_tokens": (
                                (chunk.get("prompt_eval_count") or 0)
                                + (chunk.get("eval_count") or 0)
                            ),
                        }

                self._persist_if_needed(request, assistant_text, model_id)
                yield {
                    "type": "done",
                    "used_model_id": model_id,
                    "fallback_reason": fallback_reason,
                    "attempted_models": attempted,
                    "usage": usage,
                    "created": int(time.time()),
                }
                return
            except (InferenceError, TimeoutError) as error:
                if self._is_fallback_error(error):
                    fallback_reason = str(error)
                    continue
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Inference failed: {error}",
                ) from error

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="All model attempts failed",
        )