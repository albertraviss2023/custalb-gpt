from __future__ import annotations

import asyncio
from pathlib import Path

from app.db.database import create_connection, initialize_database
from app.db.repository import Repository
from app.models.schemas import ChatCompletionRequest, MessageInput
from app.services.chat_service import ChatService
from app.services.model_registry import ModelRegistry
from app.services.ollama_client import InferenceError


class FakeOllamaClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def chat(self, *, model_ref: str, messages, temperature=None, max_tokens=None):
        self.calls.append(model_ref)
        if model_ref == "gemma4:e4b-bf16":
            raise InferenceError("CUDA out of memory")
        return {
            "message": {"content": "fallback success"},
            "prompt_eval_count": 12,
            "eval_count": 5,
        }

    async def stream_chat(self, *, model_ref: str, messages, temperature=None, max_tokens=None):
        raise NotImplementedError


def test_chat_service_falls_back_on_oom(tmp_path: Path) -> None:
    asyncio.run(_run_test(tmp_path))


async def _run_test(tmp_path: Path) -> None:
    config = tmp_path / "models.yaml"
    config.write_text(
        """
selector:
  default_model_id: e4b_16
models:
  - id: e4b_16
    display_name: E4B 16
    quantization: bf16
    tier: balanced
    runtime:
      backend: local_runtime
      model_ref: gemma4:e4b-bf16
      precision: bf16
    limits:
      max_context_tokens: 4096
      max_output_tokens: 512
  - id: e4b_8
    display_name: E4B 8
    quantization: sfp8
    tier: default
    runtime:
      backend: local_runtime
      model_ref: gemma4:e4b
      precision: int8
    limits:
      max_context_tokens: 8192
      max_output_tokens: 1024
routing:
  fallback_order: [e4b_8]
""",
        encoding="utf-8",
    )

    registry = ModelRegistry(config)
    registry.load()

    conn = create_connection(tmp_path / "app.db")
    initialize_database(conn)
    repository = Repository(conn)

    chat = repository.create_chat("Test", selected_model_id="e4b_16")

    service = ChatService(
        repository=repository,
        model_registry=registry,
        ollama_client=FakeOllamaClient(),
    )

    result = await service.complete(
        ChatCompletionRequest(
            chat_id=chat.id,
            stream=False,
            messages=[MessageInput(role="user", content="hello")],
        )
    )

    assert result.used_model_id == "e4b_8"
    assert result.text == "fallback success"
    assert "out of memory" in (result.fallback_reason or "").lower()

    saved_chat = repository.get_chat(chat.id)
    assert saved_chat is not None
    assert len(saved_chat.messages) == 2
    assert saved_chat.messages[-1].content == "fallback success"

    conn.close()
