from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.settings import settings
from app.main import app


def test_chat_telemetry_route_returns_pressure_and_compaction_state(tmp_path: Path) -> None:
    models_path = tmp_path / "models.yaml"
    models_path.write_text(
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

    database_path = tmp_path / "app.db"
    original_database_path = settings.database_path
    original_models_path = settings.model_profiles_path
    original_encryption_enabled = settings.chat_encryption_enabled
    original_encryption_key = settings.chat_encryption_key
    settings.database_path = str(database_path)
    settings.model_profiles_path = str(models_path)
    settings.chat_encryption_enabled = False
    settings.chat_encryption_key = None

    try:
        with TestClient(app) as client:
            repository = app.state.repository
            chat = repository.create_chat("Telemetry", selected_model_id="tiny")
            repository.upsert_chat_memory(
                chat_id=chat.id,
                summary_text="summary",
                summary_version=2,
                compaction_count=3,
                last_compacted_message_id="m-last",
                token_estimate=230,
            )
            repository.add_log_event(
                level="info",
                source="context_compactor",
                message="Compaction applied to chat context",
                chat_id=chat.id,
                context={"pruned_messages": 4},
            )

            response = client.get(f"/v1/chats/{chat.id}/telemetry")
            assert response.status_code == 200
            payload = response.json()
            assert payload["chat_id"] == chat.id
            assert payload["model_id"] == "tiny"
            assert payload["context_ceiling_tokens"] == 256
            assert payload["active_tokens_estimate"] == 230
            assert payload["pressure_status"] == "yellow"
            assert payload["compaction_count"] == 3
            assert payload["summary_version"] == 2
            assert payload["last_compacted_message_id"] == "m-last"
            assert len(payload["recent_events"]) >= 1
    finally:
        settings.database_path = original_database_path
        settings.model_profiles_path = original_models_path
        settings.chat_encryption_enabled = original_encryption_enabled
        settings.chat_encryption_key = original_encryption_key
