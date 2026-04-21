from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.settings import settings
from app.main import app


def test_models_route_uses_availability_aliases(tmp_path: Path) -> None:
    models_path = tmp_path / "models.yaml"
    models_path.write_text(
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
      model_ref: google/gemma-4-E4B-it
      precision: bf16
      availability_refs: [gemma4:e4b]
    limits:
      max_context_tokens: 8192
      max_output_tokens: 1024
  - id: e4b_8
    display_name: E4B 8
    quantization: int8
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
            async def fake_list_model_refs() -> set[str]:
                return {"gemma4:e4b"}

            app.state.vllm_client.list_model_refs = fake_list_model_refs

            response = client.get("/v1/models")
            assert response.status_code == 200
            payload = response.json()

            e4b_16 = next(model for model in payload["models"] if model["id"] == "e4b_16")
            assert e4b_16["available"] is True
    finally:
        settings.database_path = original_database_path
        settings.model_profiles_path = original_models_path
        settings.chat_encryption_enabled = original_encryption_enabled
        settings.chat_encryption_key = original_encryption_key
