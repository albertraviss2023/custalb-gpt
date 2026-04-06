from __future__ import annotations

from fastapi import Request

from app.db.repository import Repository
from app.services.chat_service import ChatService
from app.services.model_registry import ModelRegistry
from app.services.ollama_client import OllamaClient


def get_repository(request: Request) -> Repository:
    return request.app.state.repository


def get_model_registry(request: Request) -> ModelRegistry:
    return request.app.state.model_registry


def get_ollama_client(request: Request) -> OllamaClient:
    return request.app.state.ollama_client


def get_chat_service(request: Request) -> ChatService:
    return request.app.state.chat_service