from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.db.database import create_connection, initialize_database
from app.db.repository import Repository
from app.models.schemas import ChatCompletionRequest, MessageInput
from app.services.chat_service import ChatService
from app.services.model_registry import ModelRegistry
from app.services.vllm_client import InferenceError


class FakeInferenceClient:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.last_temperature: float | None = None
        self.last_max_tokens: int | None = None
        self.last_messages = []

    async def chat(self, *, model_ref: str, messages, temperature=None, max_tokens=None):
        self.calls.append(model_ref)
        self.last_temperature = temperature
        self.last_max_tokens = max_tokens
        self.last_messages = messages
        if model_ref == "gemma4:e4b-bf16":
            raise InferenceError("CUDA out of memory")
        # Return OpenAI/vLLM style by default, but ChatService handles both
        return {
            "choices": [{"message": {"content": "fallback success"}}],
            "usage": {
                "prompt_tokens": 12,
                "completion_tokens": 5,
            }
        }

    async def stream_chat(self, *, model_ref: str, messages, temperature=None, max_tokens=None):
        raise NotImplementedError


def test_chat_service_falls_back_on_oom(tmp_path: Path) -> None:
    asyncio.run(_run_test(tmp_path))


def test_chat_service_falls_back_when_model_missing(tmp_path: Path) -> None:
    asyncio.run(_run_missing_model_test(tmp_path))


def test_chat_service_applies_thinking_and_length_controls(tmp_path: Path) -> None:
    asyncio.run(_run_controls_test(tmp_path))


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
        inference_client=FakeInferenceClient(),
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
    assert result.telemetry["context_ceiling_tokens"] == 4096

    saved_chat = repository.get_chat(chat.id)
    assert saved_chat is not None
    assert len(saved_chat.messages) == 2
    assert saved_chat.messages[-1].content == "fallback success"
    assert saved_chat.title == "Test"

    conn.close()


async def _run_missing_model_test(tmp_path: Path) -> None:
    config = tmp_path / "models.yaml"
    config.write_text(
        """
selector:
  default_model_id: e4b_8
models:
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
  - id: e2b
    display_name: E2B
    quantization: q4
    tier: fast
    runtime:
      backend: local_runtime
      model_ref: gemma4:e2b
      precision: int4
    limits:
      max_context_tokens: 8192
      max_output_tokens: 512
routing:
  fallback_order: [e2b]
""",
        encoding="utf-8",
    )

    class MissingPrimaryClient(FakeInferenceClient):
        async def chat(self, *, model_ref: str, messages, temperature=None, max_tokens=None):
            self.calls.append(model_ref)
            if model_ref == "gemma4:e4b":
                raise InferenceError('{"error":"model \\"gemma4:e4b\\" not found"}')
            return {
                "message": {"content": "fallback works"},
                "prompt_eval_count": 10,
                "eval_count": 4,
            }

    registry = ModelRegistry(config)
    registry.load()
    conn = create_connection(tmp_path / "app.db")
    initialize_database(conn)
    repository = Repository(conn)
    service = ChatService(
        repository=repository,
        model_registry=registry,
        inference_client=MissingPrimaryClient(),
    )

    result = await service.complete(
        ChatCompletionRequest(
            stream=False,
            model="e4b_8",
            messages=[MessageInput(role="user", content="hello")],
        )
    )

    assert result.used_model_id == "e2b"
    assert result.text == "fallback works"
    assert result.telemetry["pressure_status"] in {"green", "yellow", "red"}
    conn.close()


async def _run_controls_test(tmp_path: Path) -> None:
    config = tmp_path / "models.yaml"
    config.write_text(
        """
selector:
  default_model_id: e4b_8
models:
  - id: e4b_8
    display_name: E4B 8
    quantization: sfp8
    tier: default
    runtime:
      backend: local_runtime
      model_ref: gemma4:e4b
      precision: int8
    limits:
      max_context_tokens: 16384
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
    client = FakeInferenceClient()
    service = ChatService(
        repository=repository,
        model_registry=registry,
        inference_client=client,
    )

    await service.complete(
        ChatCompletionRequest(
            stream=False,
            model="e4b_8",
            thinking_level="fast",
            response_length="concise",
            messages=[MessageInput(role="user", content="quick answer")],
        )
    )

    assert client.last_temperature is not None
    assert client.last_temperature <= 0.2
    assert client.last_max_tokens is not None
    assert client.last_max_tokens <= 220
    assert client.last_messages[0]["role"] == "system"
    assert "Response policy" in client.last_messages[0]["content"]
    conn.close()


def test_chat_service_trims_history_to_budget(tmp_path: Path) -> None:
    asyncio.run(_run_budget_trim_test(tmp_path))


def test_chat_service_resumes_from_persisted_context(tmp_path: Path) -> None:
    asyncio.run(_run_resume_context_test(tmp_path))


def test_chat_service_compacts_when_near_ceiling(tmp_path: Path) -> None:
    asyncio.run(_run_compaction_test(tmp_path))


def test_chat_service_cbi_applies_conservative_context_and_output_limits(tmp_path: Path) -> None:
    asyncio.run(_run_cbi_limits_test(tmp_path))


def test_chat_service_regenerate_replaces_assistant_message(tmp_path: Path) -> None:
    asyncio.run(_run_regenerate_replace_test(tmp_path))


def test_chat_service_cbi_silence_does_not_get_high_score(tmp_path: Path) -> None:
    asyncio.run(_run_cbi_silence_scoring_test(tmp_path))


async def _run_budget_trim_test(tmp_path: Path) -> None:
    config = tmp_path / "models.yaml"
    config.write_text(
        """
selector:
  default_model_id: tiny
models:
  - id: tiny
    display_name: Tiny
    quantization: q4
    tier: fast
    runtime:
      backend: local_runtime
      model_ref: tiny:model
      precision: int4
    limits:
      max_context_tokens: 256
      max_output_tokens: 128
routing:
  fallback_order: [tiny]
""",
        encoding="utf-8",
    )

    registry = ModelRegistry(config)
    registry.load()
    conn = create_connection(tmp_path / "app.db")
    initialize_database(conn)
    repository = Repository(conn)
    client = FakeInferenceClient()
    service = ChatService(
        repository=repository,
        model_registry=registry,
        inference_client=client,
    )

    messages = [MessageInput(role="user", content=f"turn-{i} " + ("x" * 240)) for i in range(12)]
    result = await service.complete(
        ChatCompletionRequest(
            stream=False,
            model="tiny",
            messages=messages,
            response_length="detailed",
        )
    )

    assert result.used_model_id == "tiny"
    assert result.telemetry["context_ceiling_tokens"] == 256
    assert result.telemetry["trimmed_messages"] > 0
    conn.close()


async def _run_resume_context_test(tmp_path: Path) -> None:
    config = tmp_path / "models.yaml"
    config.write_text(
        """
selector:
  default_model_id: e4b_8
models:
  - id: e4b_8
    display_name: E4B 8
    quantization: sfp8
    tier: default
    runtime:
      backend: local_runtime
      model_ref: gemma4:e4b
      precision: int8
    limits:
      max_context_tokens: 4096
      max_output_tokens: 512
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
    chat = repository.create_chat("resume", selected_model_id="e4b_8")
    repository.add_message(chat.id, "user", "Earlier user note", None)
    repository.add_message(chat.id, "assistant", "Earlier assistant note", "e4b_8")
    repository.upsert_chat_memory(
        chat_id=chat.id,
        summary_text="User prefers concise answers.",
        summary_version=1,
        compaction_count=1,
        last_compacted_message_id=None,
        token_estimate=128,
    )

    client = FakeInferenceClient()
    service = ChatService(
        repository=repository,
        model_registry=registry,
        inference_client=client,
    )

    await service.complete(
        ChatCompletionRequest(
            stream=False,
            chat_id=chat.id,
            messages=[MessageInput(role="user", content="New question now")],
        )
    )

    text_segments = []
    for message in client.last_messages:
        content = message.get("content")
        if isinstance(content, str):
            text_segments.append(content)
    joined = "\n".join(text_segments)
    assert "User prefers concise answers." in joined
    assert "Earlier user note" in joined
    assert "Earlier assistant note" in joined
    assert "New question now" in joined
    conn.close()


async def _run_compaction_test(tmp_path: Path) -> None:
    config = tmp_path / "models.yaml"
    config.write_text(
        """
selector:
  default_model_id: tiny
models:
  - id: tiny
    display_name: Tiny
    quantization: q4
    tier: fast
    runtime:
      backend: local_runtime
      model_ref: tiny:model
      precision: int4
    limits:
      max_context_tokens: 256
      max_output_tokens: 128
routing:
  fallback_order: [tiny]
""",
        encoding="utf-8",
    )

    registry = ModelRegistry(config)
    registry.load()
    conn = create_connection(tmp_path / "app.db")
    initialize_database(conn)
    repository = Repository(conn)
    chat = repository.create_chat("compact", selected_model_id="tiny")

    for i in range(18):
        repository.add_message(chat.id, "user", f"user-{i} " + ("x" * 120), None)
        repository.add_message(chat.id, "assistant", f"assistant-{i} " + ("y" * 120), "tiny")

    client = FakeInferenceClient()
    service = ChatService(
        repository=repository,
        model_registry=registry,
        inference_client=client,
    )
    result = await service.complete(
        ChatCompletionRequest(
            stream=False,
            chat_id=chat.id,
            messages=[MessageInput(role="user", content="latest request")],
        )
    )

    memory = repository.get_chat_memory(chat.id)
    assert memory is not None
    assert memory["compaction_count"] >= 1
    assert memory["summary_version"] >= 1
    assert "Compacted history notes" in str(memory["summary_text"])

    after = repository.get_chat(chat.id)
    assert after is not None
    assert len(after.messages) < 36  # stale rows pruned from active message graph
    assert result.telemetry.get("compaction_applied") is True
    conn.close()


async def _run_cbi_limits_test(tmp_path: Path) -> None:
    config = tmp_path / "models.yaml"
    config.write_text(
        """
selector:
  default_model_id: e4b_8
models:
  - id: e4b_8
    display_name: E4B 8
    quantization: sfp8
    tier: default
    runtime:
      backend: local_runtime
      model_ref: gemma4:e4b
      precision: int8
    limits:
      max_context_tokens: 4096
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
    client = FakeInferenceClient()
    service = ChatService(
        repository=repository,
        model_registry=registry,
        inference_client=client,
    )

    result = await service.complete(
        ChatCompletionRequest(
            stream=False,
            model="e4b_8",
            addon_id="competency_interview_coach",
            response_length="detailed",
            thinking_level="deep",
            messages=[MessageInput(role="user", content="Start CBI practice now")],
        )
    )

    assert result.telemetry["context_ceiling_tokens"] == 2048
    assert client.last_max_tokens is not None
    assert client.last_max_tokens <= 320
    conn.close()


async def _run_regenerate_replace_test(tmp_path: Path) -> None:
    config = tmp_path / "models.yaml"
    config.write_text(
        """
selector:
  default_model_id: e4b_8
models:
  - id: e4b_8
    display_name: E4B 8
    quantization: sfp8
    tier: default
    runtime:
      backend: local_runtime
      model_ref: gemma4:e4b
      precision: int8
    limits:
      max_context_tokens: 4096
      max_output_tokens: 1024
routing:
  fallback_order: [e4b_8]
""",
        encoding="utf-8",
    )

    class RegenerateClient(FakeInferenceClient):
        async def chat(self, *, model_ref: str, messages, temperature=None, max_tokens=None):
            self.calls.append(model_ref)
            return {
                "choices": [{"message": {"content": "fresh regenerated answer"}}],
                "usage": {"prompt_tokens": 8, "completion_tokens": 4},
            }

    registry = ModelRegistry(config)
    registry.load()
    conn = create_connection(tmp_path / "app.db")
    initialize_database(conn)
    repository = Repository(conn)
    chat = repository.create_chat("regen", selected_model_id="e4b_8")
    repository.add_message(chat.id, "user", "How do I tune this model?", None)
    original = repository.add_message(chat.id, "assistant", "Old answer", "e4b_8")

    service = ChatService(
        repository=repository,
        model_registry=registry,
        inference_client=RegenerateClient(),
    )

    await service.complete(
        ChatCompletionRequest(
            stream=False,
            chat_id=chat.id,
            model="e4b_8",
            regenerate_target_message_id=original.id,
            messages=[MessageInput(role="user", content="How do I tune this model?")],
        )
    )

    refreshed = repository.get_chat(chat.id)
    assert refreshed is not None
    assert len(refreshed.messages) == 2
    assert refreshed.messages[1].id == original.id
    assert refreshed.messages[1].content == "fresh regenerated answer"
    conn.close()


async def _run_cbi_silence_scoring_test(tmp_path: Path) -> None:
    config = tmp_path / "models.yaml"
    config.write_text(
        """
selector:
  default_model_id: e4b_8
models:
  - id: e4b_8
    display_name: E4B 8
    quantization: sfp8
    tier: default
    runtime:
      backend: local_runtime
      model_ref: gemma4:e4b
      precision: int8
    limits:
      max_context_tokens: 4096
      max_output_tokens: 1024
routing:
  fallback_order: [e4b_8]
""",
        encoding="utf-8",
    )

    class CbiInflatedClient(FakeInferenceClient):
        async def chat(self, *, model_ref: str, messages, temperature=None, max_tokens=None):
            self.calls.append(model_ref)
            inflated = (
                'CBI_SCORECARD_JSON:{"role":"Senior Data Scientist","overall_readiness_0_to_100":97,'
                '"competencies":[{"name":"Communication","weight":20,"score_1_to_5":5,'
                '"evidence":"Excellent","gaps":"None","improvement":"Keep going"}],'
                '"panel_summary":"Excellent candidate","next_best_question":"None"}'
            )
            return {
                "choices": [{"message": {"content": inflated}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 5},
            }

    registry = ModelRegistry(config)
    registry.load()
    conn = create_connection(tmp_path / "app.db")
    initialize_database(conn)
    repository = Repository(conn)
    service = ChatService(
        repository=repository,
        model_registry=registry,
        inference_client=CbiInflatedClient(),
    )

    result = await service.complete(
        ChatCompletionRequest(
            stream=False,
            model="e4b_8",
            addon_id="competency_interview_coach",
            messages=[MessageInput(role="user", content="End this interview now and generate final CBI performance report now.")],
        )
    )

    marker = "CBI_SCORECARD_JSON:"
    assert marker in result.text
    raw = result.text.split(marker, 1)[1]
    parsed = json.loads(raw)
    assert int(parsed["overall_readiness_0_to_100"]) <= 20
    assert int(parsed["competencies"][0]["score_1_to_5"]) == 1
    conn.close()
