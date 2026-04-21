from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from app.api.dependencies import get_tts_service
from app.core.auth import require_api_key
from app.models.schemas import TtsSynthesisRequest
from app.services.tts_service import TTSService

router = APIRouter(prefix="/v1/tts", tags=["tts"], dependencies=[Depends(require_api_key)])


@router.post("/speak")
async def speak(
    payload: TtsSynthesisRequest,
    tts_service: TTSService = Depends(get_tts_service),
) -> Response:
    result = await tts_service.synthesize(
        text=payload.text,
        speaker_name=payload.speaker_name,
        voice_id=payload.voice_id,
        accent=payload.accent,
        tone=payload.tone,
        speaking_style=payload.speaking_style,
    )
    return Response(
        content=result.audio_bytes,
        media_type=result.media_type,
        headers={"Cache-Control": "no-store"},
    )
