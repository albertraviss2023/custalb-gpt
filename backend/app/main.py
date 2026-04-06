from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.chats import router as chats_router
from app.api.routes.completions import router as completions_router
from app.api.routes.health import router as health_router
from app.api.routes.models import router as models_router
from app.core.settings import settings
from app.db.database import create_connection, initialize_database
from app.db.repository import Repository
from app.services.chat_service import ChatService
from app.services.model_registry import ModelRegistry
from app.services.ollama_client import OllamaClient


@asynccontextmanager
async def lifespan(app: FastAPI):
    model_registry = ModelRegistry(settings.resolved_model_profiles_path())
    model_registry.load()

    connection = create_connection(settings.resolved_database_path())
    initialize_database(connection)

    repository = Repository(connection)
    if not model_registry.exists(repository.get_default_model_id(model_registry.default_model_id)):
        repository.set_default_model_id(model_registry.default_model_id)

    ollama_client = OllamaClient(
        base_url=settings.ollama_base_url,
        timeout_seconds=settings.ollama_request_timeout_seconds,
    )

    chat_service = ChatService(
        repository=repository,
        model_registry=model_registry,
        ollama_client=ollama_client,
    )

    app.state.model_registry = model_registry
    app.state.repository = repository
    app.state.ollama_client = ollama_client
    app.state.chat_service = chat_service

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