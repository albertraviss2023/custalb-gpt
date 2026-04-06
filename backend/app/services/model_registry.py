from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.models.schemas import ModelDescriptor


@dataclass(slots=True)
class RuntimeConfig:
    backend: str
    model_ref: str
    precision: str


@dataclass(slots=True)
class ModelLimits:
    max_context_tokens: int
    max_output_tokens: int


@dataclass(slots=True)
class ModelProfile:
    id: str
    display_name: str
    quantization: str
    tier: str
    description: str
    runtime: RuntimeConfig
    limits: ModelLimits


class ModelRegistry:
    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self.default_model_id: str = ""
        self.allow_per_chat_override: bool = True
        self.hot_switch_enabled: bool = True
        self.fallback_order: list[str] = []
        self.timeout_fallback_to: str | None = None
        self.timeout_seconds: int = 90
        self._profiles: dict[str, ModelProfile] = {}

    def load(self) -> None:
        if not self.config_path.exists():
            raise FileNotFoundError(f"Model profile config not found: {self.config_path}")

        raw = yaml.safe_load(self.config_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("Invalid model profile config: expected mapping")

        selector = raw.get("selector", {})
        self.default_model_id = str(selector.get("default_model_id", ""))
        self.allow_per_chat_override = bool(selector.get("allow_per_chat_override", True))
        self.hot_switch_enabled = bool(selector.get("hot_switch_enabled", True))

        routing = raw.get("routing", {})
        self.fallback_order = [str(value) for value in routing.get("fallback_order", [])]
        self.timeout_fallback_to = routing.get("timeout_fallback_to")
        self.timeout_seconds = int(routing.get("on_timeout_seconds", 90))

        profiles: dict[str, ModelProfile] = {}
        for item in raw.get("models", []):
            runtime = item.get("runtime", {})
            limits = item.get("limits", {})
            profile = ModelProfile(
                id=str(item["id"]),
                display_name=str(item["display_name"]),
                quantization=str(item["quantization"]),
                tier=str(item["tier"]),
                description=str(item.get("description", "")),
                runtime=RuntimeConfig(
                    backend=str(runtime.get("backend", "local_runtime")),
                    model_ref=str(runtime.get("model_ref", "")),
                    precision=str(runtime.get("precision", "unknown")),
                ),
                limits=ModelLimits(
                    max_context_tokens=int(limits.get("max_context_tokens", 4096)),
                    max_output_tokens=int(limits.get("max_output_tokens", 512)),
                ),
            )
            profiles[profile.id] = profile

        if self.default_model_id not in profiles:
            raise ValueError("Default model id not present in model profiles")

        for model_id in self.fallback_order:
            if model_id not in profiles:
                raise ValueError(f"Fallback model id not present in model profiles: {model_id}")

        self._profiles = profiles

    def list_descriptors(self) -> list[ModelDescriptor]:
        return [
            ModelDescriptor(
                id=profile.id,
                display_name=profile.display_name,
                quantization=profile.quantization,
                tier=profile.tier,
                description=profile.description,
            )
            for profile in self._profiles.values()
        ]

    def get(self, model_id: str) -> ModelProfile:
        if model_id not in self._profiles:
            raise KeyError(f"Unknown model id: {model_id}")
        return self._profiles[model_id]

    def exists(self, model_id: str) -> bool:
        return model_id in self._profiles

    def build_fallback_chain(self, requested_model_id: str) -> list[str]:
        chain: list[str] = [requested_model_id]
        for model_id in self.fallback_order:
            if model_id not in chain:
                chain.append(model_id)
        return chain

    def get_timeout_fallback(self) -> str | None:
        if self.timeout_fallback_to and self.timeout_fallback_to in self._profiles:
            return self.timeout_fallback_to
        return None