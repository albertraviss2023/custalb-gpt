from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_tts_service
from app.api.routes.tts import router as tts_router
from app.services.tts_service import TtsResult


class _StubTtsService:
    async def synthesize(
        self,
        *,
        text: str,
        speaker_name: str | None,
        voice_id: str | None,
        accent: str | None,
        tone: str | None,
        speaking_style: str | None,
    ) -> TtsResult:
        return TtsResult(audio_bytes=b"WAVDATA", media_type="audio/wav")


def test_tts_route_returns_audio_bytes() -> None:
    app = FastAPI()
    app.include_router(tts_router)
    app.dependency_overrides[get_tts_service] = lambda: _StubTtsService()
    client = TestClient(app)

    response = client.post(
        "/v1/tts/speak",
        json={
            "text": "Hello candidate",
            "speaker_name": "Dr. Elena Sokolov",
            "voice_id": "panel-chair",
            "accent": "en-gb",
            "tone": "formal",
            "speaking_style": "structured",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.content == b"WAVDATA"
