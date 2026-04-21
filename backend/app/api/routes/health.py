from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import get_tts_service, get_vllm_client
from app.models.schemas import HealthResponse
from app.services.tts_service import TTSService
from app.services.vllm_client import VLLMClient

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthResponse)
async def health(
    vllm_client: VLLMClient = Depends(get_vllm_client),
    tts_service: TTSService = Depends(get_tts_service),
) -> HealthResponse:
    reachable = await vllm_client.ping()
    tts_reachable = await tts_service.health()
    return HealthResponse(
        status="ok",
        version="0.1.0",
        runtime_reachable=reachable,
        tts_reachable=tts_reachable,
    )
