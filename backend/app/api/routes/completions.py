from __future__ import annotations

import json
import time
import uuid
from typing import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_chat_service
from app.core.auth import require_api_key
from app.models.schemas import (
    ChatCompletionChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionUsage,
    MessageInput,
)
from app.services.chat_service import ChatService

router = APIRouter(prefix="/v1", tags=["chat"], dependencies=[Depends(require_api_key)])


def _sse_line(data: dict[str, object] | str) -> str:
    if isinstance(data, str):
        return f"data: {data}\n\n"
    return f"data: {json.dumps(data)}\n\n"


@router.post("/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(
    payload: ChatCompletionRequest,
    chat_service: ChatService = Depends(get_chat_service),
):
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    created_at = int(time.time())

    if payload.stream:
        async def event_generator() -> AsyncIterator[str]:
            try:
                async for event in chat_service.stream_complete(payload):
                    if event["type"] == "token":
                        chunk = {
                            "id": completion_id,
                            "object": "chat.completion.chunk",
                            "created": created_at,
                            "model": event["used_model_id"],
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {"content": event["token"]},
                                    "finish_reason": None,
                                }
                            ],
                        }
                        yield _sse_line(chunk)
                    elif event["type"] == "done":
                        final_chunk = {
                            "id": completion_id,
                            "object": "chat.completion.chunk",
                            "created": event["created"],
                            "model": event["used_model_id"],
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {},
                                    "finish_reason": "stop",
                                }
                            ],
                            "metadata": {
                                "fallback_reason": event["fallback_reason"],
                                "attempted_models": event["attempted_models"],
                                "usage": event["usage"],
                                "telemetry": event.get("telemetry", {}),
                            },
                        }
                        yield _sse_line(final_chunk)
                        yield _sse_line("[DONE]")
            except Exception:
                try:
                    recovery = await chat_service.complete(payload.model_copy(update={"stream": False}))
                    recovery_chunk = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": recovery.used_model_id,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": recovery.text},
                                "finish_reason": None,
                            }
                        ],
                        "metadata": {
                            "stream_error": True,
                            "recovered_via_non_stream": True,
                            "attempted_models": recovery.attempted_models,
                        },
                    }
                    yield _sse_line(recovery_chunk)
                    yield _sse_line("[DONE]")
                except Exception:
                    error_chunk = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": payload.model or "unknown",
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": "I hit a streaming error. Please resend once and I will retry."},
                                "finish_reason": None,
                            }
                        ],
                        "metadata": {"stream_error": True},
                    }
                    yield _sse_line(error_chunk)
                    yield _sse_line("[DONE]")

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    result = await chat_service.complete(payload)
    response = ChatCompletionResponse(
        id=completion_id,
        created=created_at,
        model=result.used_model_id,
        choices=[
            ChatCompletionChoice(
                index=0,
                message=MessageInput(role="assistant", content=result.text),
                finish_reason="stop",
            )
        ],
        usage=ChatCompletionUsage(**result.usage),
        metadata={
            "fallback_reason": result.fallback_reason,
            "attempted_models": result.attempted_models,
            "telemetry": result.telemetry,
        },
    )
    return response
