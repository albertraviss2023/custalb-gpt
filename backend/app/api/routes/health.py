from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import get_ollama_client
from app.models.schemas import HealthResponse
from app.services.ollama_client import OllamaClient

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthResponse)
async def health(ollama_client: OllamaClient = Depends(get_ollama_client)) -> HealthResponse:
    reachable = await ollama_client.ping()
    return HealthResponse(status="ok", version="0.1.0", ollama_reachable=reachable)