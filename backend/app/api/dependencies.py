from __future__ import annotations

from fastapi import Request

from app.db.repository import Repository
from app.services.chat_service import ChatService
from app.services.addon_store import AddonStore
from app.services.model_registry import ModelRegistry
from app.services.vllm_client import VLLMClient


def get_repository(request: Request) -> Repository:
    return request.app.state.repository


def get_model_registry(request: Request) -> ModelRegistry:
    return request.app.state.model_registry


def get_vllm_client(request: Request) -> VLLMClient:
    return request.app.state.vllm_client


def get_chat_service(request: Request) -> ChatService:
    return request.app.state.chat_service


def get_addon_store(request: Request) -> AddonStore:
    return request.app.state.addon_store
