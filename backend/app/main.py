from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.chats import router as chats_router
from app.api.routes.completions import router as completions_router
from app.api.routes.health import router as health_router
from app.api.routes.models import router as models_router
from app.api.routes.logs import router as logs_router
from app.api.routes.telemetry import router as telemetry_router
from app.api.routes.tts import router as tts_router
from app.core.settings import settings
from app.db.database import create_connection, initialize_database
from app.db.repository import Repository
from app.services.chat_service import ChatService
from app.services.addon_store import AddonStore
from app.services.model_registry import ModelRegistry
from app.services.message_cipher import MessageCipher
from app.services.tts_service import TTSService
from app.services.vllm_client import VLLMClient
from app.api.routes.addons import router as addons_router
from app.api.routes.files import router as files_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    model_registry = ModelRegistry(settings.resolved_model_profiles_path())
    model_registry.load()

    connection = create_connection(settings.resolved_database_path())
    initialize_database(connection)

    cipher: MessageCipher | None = None
    if settings.chat_encryption_enabled:
        if not settings.chat_encryption_key:
            raise ValueError("GOI_CHAT_ENCRYPTION_ENABLED=true requires GOI_CHAT_ENCRYPTION_KEY")
        cipher = MessageCipher.from_optional_key(settings.chat_encryption_key)

    repository = Repository(connection, message_cipher=cipher)
    if not model_registry.exists(repository.get_default_model_id(model_registry.default_model_id)):
        repository.set_default_model_id(model_registry.default_model_id)

    vllm_client = VLLMClient(
        base_url=settings.vllm_base_url,
        timeout_seconds=settings.vllm_request_timeout_seconds,
    )
    addon_store = AddonStore()
    tts_service = TTSService(
        provider=settings.tts_provider,
        kokoro_base_url=settings.tts_kokoro_base_url,
        kokoro_path=settings.tts_kokoro_synthesize_path,
        xtts_base_url=settings.tts_xtts_base_url,
        xtts_path=settings.tts_xtts_synthesize_path,
        timeout_seconds=settings.tts_timeout_seconds,
    )

    chat_service = ChatService(
        repository=repository,
        model_registry=model_registry,
        inference_client=vllm_client,
        addon_store=addon_store,
    )

    app.state.model_registry = model_registry
    app.state.repository = repository
    app.state.vllm_client = vllm_client
    app.state.chat_service = chat_service
    app.state.addon_store = addon_store
    app.state.tts_service = tts_service

    try:
        yield
    finally:
        connection.close()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(models_router)
app.include_router(chats_router)
app.include_router(completions_router)
app.include_router(addons_router)
app.include_router(files_router)
app.include_router(logs_router)
app.include_router(telemetry_router)
app.include_router(tts_router)
