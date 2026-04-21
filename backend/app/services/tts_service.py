from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import HTTPException, status


@dataclass(slots=True)
class TtsResult:
    audio_bytes: bytes
    media_type: str


@dataclass(slots=True)
class TtsProviderConfig:
    name: str
    base_url: str
    synthesize_path: str
    timeout_seconds: int


class TTSService:
    def __init__(
        self,
        *,
        provider: str,
        kokoro_base_url: str,
        kokoro_path: str,
        xtts_base_url: str,
        xtts_path: str,
        timeout_seconds: int,
    ) -> None:
        chosen = (provider or "").strip().lower()
        if chosen not in {"kokoro", "xtts"}:
            chosen = "kokoro"
        self.provider_name = chosen
        self.timeout_seconds = timeout_seconds
        self.kokoro = TtsProviderConfig(
            name="kokoro",
            base_url=kokoro_base_url.rstrip("/"),
            synthesize_path=kokoro_path if kokoro_path.startswith("/") else f"/{kokoro_path}",
            timeout_seconds=timeout_seconds,
        )
        self.xtts = TtsProviderConfig(
            name="xtts",
            base_url=xtts_base_url.rstrip("/"),
            synthesize_path=xtts_path if xtts_path.startswith("/") else f"/{xtts_path}",
            timeout_seconds=timeout_seconds,
        )

    def _active(self) -> TtsProviderConfig:
        return self.xtts if self.provider_name == "xtts" else self.kokoro

    async def health(self) -> bool:
        cfg = self._active()
        try:
            async with httpx.AsyncClient(timeout=min(cfg.timeout_seconds, 6.0)) as client:
                response = await client.get(f"{cfg.base_url}/health")
                if response.status_code < 500:
                    return True
        except Exception:
            return False
        return False

    @staticmethod
    def _payload(
        *,
        text: str,
        speaker_name: str | None,
        voice_id: str | None,
        accent: str | None,
        tone: str | None,
        speaking_style: str | None,
    ) -> dict[str, Any]:
        return {
            "text": text,
            "speaker_name": speaker_name,
            "voice_id": voice_id,
            "accent": accent,
            "tone": tone,
            "speaking_style": speaking_style,
            "format": "wav",
        }

    @staticmethod
    def _extract_json_audio(payload: dict[str, Any]) -> TtsResult:
        raw = payload.get("audio_base64")
        if isinstance(raw, str) and raw.strip():
            return TtsResult(audio_bytes=base64.b64decode(raw), media_type="audio/wav")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Local TTS service returned unsupported payload format",
        )

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
        cfg = self._active()
        payload = self._payload(
            text=text,
            speaker_name=speaker_name,
            voice_id=voice_id,
            accent=accent,
            tone=tone,
            speaking_style=speaking_style,
        )
        try:
            async with httpx.AsyncClient(timeout=cfg.timeout_seconds) as client:
                response = await client.post(
                    f"{cfg.base_url}{cfg.synthesize_path}",
                    json=payload,
                )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Local TTS provider '{cfg.name}' is unreachable: {exc}",
            ) from exc

        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Local TTS provider '{cfg.name}' failed with status {response.status_code}",
            )

        content_type = (response.headers.get("content-type") or "").lower()
        if content_type.startswith("audio/"):
            return TtsResult(audio_bytes=response.content, media_type=content_type.split(";")[0])

        try:
            data = response.json()
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Local TTS provider '{cfg.name}' returned non-audio response",
            ) from exc
        if not isinstance(data, dict):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Local TTS provider '{cfg.name}' returned invalid response shape",
            )
        return self._extract_json_audio(data)
