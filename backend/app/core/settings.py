from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Personal GOI API"
    environment: str = "dev"
    host: str = "0.0.0.0"
    port: int = 8000

    vllm_base_url: str = "http://vllm:8000"
    vllm_request_timeout_seconds: int = 180

    api_key: str | None = None

    database_path: str = "./data/app.db"
    model_profiles_path: str = "../config/model_profiles.yaml"
    uploads_dir: str = "./data/uploads"
    max_upload_size_bytes: int = 500 * 1024 * 1024 * 1024
    chat_encryption_enabled: bool = False
    chat_encryption_key: str | None = None
    tts_provider: str = "kokoro"
    tts_timeout_seconds: int = 30
    tts_kokoro_base_url: str = "http://goi-kokoro-tts:8880"
    tts_kokoro_synthesize_path: str = "/v1/audio/speech"
    tts_xtts_base_url: str = "http://goi-xtts-tts:8020"
    tts_xtts_synthesize_path: str = "/api/tts"

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

    def resolved_uploads_dir(self) -> Path:
        path = Path(self.uploads_dir)
        if path.is_absolute():
            return path
        return Path.cwd() / path


settings = Settings()
