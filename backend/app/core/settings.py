from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Personal GOI API"
    environment: str = "dev"
    host: str = "0.0.0.0"
    port: int = 8000

    ollama_base_url: str = "http://ollama:11434"
    ollama_request_timeout_seconds: int = 120

    api_key: str | None = None

    database_path: str = "./data/app.db"
    model_profiles_path: str = "../config/model_profiles.yaml"

    model_config = SettingsConfigDict(env_file=".env", env_prefix="GOI_", extra="ignore")

    def resolved_database_path(self) -> Path:
        path = Path(self.database_path)
        if path.is_absolute():
            return path
        return Path.cwd() / path

    def resolved_model_profiles_path(self) -> Path:
        path = Path(self.model_profiles_path)
        if path.is_absolute():
            return path

        # Resolve relative to process CWD first, then fallback to repo-root style.
        candidate = Path.cwd() / path
        if candidate.exists():
            return candidate

        return Path.cwd().parent / "config" / "model_profiles.yaml"


settings = Settings()