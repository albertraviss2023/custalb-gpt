from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.settings import settings
from app.main import app


def _write_models(path: Path) -> None:
    path.write_text(
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
      max_context_tokens: 4096
      max_output_tokens: 512
routing:
  fallback_order: [tiny]
""",
        encoding="utf-8",
    )


def test_create_chat_can_inherit_recent_context(tmp_path: Path) -> None:
    models_path = tmp_path / "models.yaml"
    _write_models(models_path)
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
            source = client.post("/v1/chats", json={"title": "Source", "selected_model_id": "tiny"})
            assert source.status_code == 201
            source_id = source.json()["id"]

            app.state.repository.add_message(source_id, "user", "hello from source", None)
            app.state.repository.add_message(source_id, "assistant", "source answer", "tiny")
            app.state.repository.upsert_chat_memory(
                chat_id=source_id,
                summary_text="source summary",
                summary_version=2,
                compaction_count=1,
                last_compacted_message_id=None,
                token_estimate=120,
            )

            created = client.post(
                "/v1/chats",
                json={
                    "title": "Inherited",
                    "selected_model_id": "tiny",
                    "inherit_from_chat_id": source_id,
                    "inherit_recent_messages": 12,
                },
            )
            assert created.status_code == 201
            inherited_id = created.json()["id"]

            inherited_chat = client.get(f"/v1/chats/{inherited_id}")
            assert inherited_chat.status_code == 200
            payload = inherited_chat.json()
            assert [m["content"] for m in payload["messages"]] == ["hello from source", "source answer"]

            inherited_memory = app.state.repository.get_chat_memory(inherited_id)
            assert inherited_memory is not None
            assert inherited_memory["summary_text"] == "source summary"
            assert inherited_memory["summary_version"] == 2
    finally:
        settings.database_path = original_database_path
        settings.model_profiles_path = original_models_path
        settings.chat_encryption_enabled = original_encryption_enabled
        settings.chat_encryption_key = original_encryption_key


def test_create_chat_inheritance_requires_existing_source(tmp_path: Path) -> None:
    models_path = tmp_path / "models.yaml"
    _write_models(models_path)
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
            response = client.post(
                "/v1/chats",
                json={
                    "title": "Inherited",
                    "selected_model_id": "tiny",
                    "inherit_from_chat_id": "missing-chat",
                    "inherit_recent_messages": 12,
                },
            )
            assert response.status_code == 404
            assert response.json()["detail"] == "Source chat not found"
    finally:
        settings.database_path = original_database_path
        settings.model_profiles_path = original_models_path
        settings.chat_encryption_enabled = original_encryption_enabled
        settings.chat_encryption_key = original_encryption_key


def test_create_chat_can_inherit_summary_only(tmp_path: Path) -> None:
    models_path = tmp_path / "models.yaml"
    _write_models(models_path)
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
            source = client.post("/v1/chats", json={"title": "Source Summary", "selected_model_id": "tiny"})
            assert source.status_code == 201
            source_id = source.json()["id"]

            app.state.repository.add_message(source_id, "user", "I worked on a delivery roadmap and reduced delays.", None)
            app.state.repository.add_message(source_id, "assistant", "Noted. We can frame this with STAR.", "tiny")

            created = client.post(
                "/v1/chats",
                json={
                    "title": "Inherited Summary Only",
                    "selected_model_id": "tiny",
                    "inherit_from_chat_id": source_id,
                    "inherit_recent_messages": 0,
                },
            )
            assert created.status_code == 201
            inherited_id = created.json()["id"]

            inherited_chat = client.get(f"/v1/chats/{inherited_id}")
            assert inherited_chat.status_code == 200
            payload = inherited_chat.json()
            assert payload["messages"] == []

            inherited_memory = app.state.repository.get_chat_memory(inherited_id)
            assert inherited_memory is not None
            assert "Inherited chat summary" in str(inherited_memory["summary_text"])
    finally:
        settings.database_path = original_database_path
        settings.model_profiles_path = original_models_path
        settings.chat_encryption_enabled = original_encryption_enabled
        settings.chat_encryption_key = original_encryption_key
