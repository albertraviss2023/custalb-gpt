from __future__ import annotations

from pathlib import Path

from app.services.model_registry import ModelRegistry


def test_model_registry_loads_profiles(tmp_path: Path) -> None:
    config = tmp_path / "models.yaml"
    config.write_text(
        """
selector:
  default_model_id: e4b
models:
  - id: e4b
    display_name: E4B 8-bit
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
  fallback_order: [e4b]
""",
        encoding="utf-8",
    )

    registry = ModelRegistry(config)
    registry.load()

    assert registry.default_model_id == "e4b"
    assert registry.exists("e4b")
    assert registry.list_descriptors()[0].display_name == "E4B 8-bit"