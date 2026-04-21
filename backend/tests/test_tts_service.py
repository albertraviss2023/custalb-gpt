from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

import httpx
from fastapi import HTTPException
import pytest

from app.services.tts_service import TTSService


class _FakeResponse:
    def __init__(self, status_code: int = 200, content: bytes = b"", headers: dict[str, str] | None = None, payload: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}
        self._payload = payload

    def json(self) -> dict[str, Any]:
        if self._payload is None:
            raise ValueError("No payload")
        return self._payload


class _FakeAsyncClient:
    def __init__(self, *, get_response: _FakeResponse | None = None, post_response: _FakeResponse | None = None, post_exc: Exception | None = None) -> None:
        self._get_response = get_response
        self._post_response = post_response
        self._post_exc = post_exc

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        return None

    async def get(self, url: str) -> _FakeResponse:
        if self._get_response is None:
            raise httpx.ConnectError("down")
        return self._get_response

    async def post(self, url: str, json: dict[str, Any]) -> _FakeResponse:
        if self._post_exc:
            raise self._post_exc
        if self._post_response is None:
            raise httpx.ConnectError("down")
        return self._post_response


def test_tts_health_true_for_reachable_service() -> None:
    service = TTSService(
        provider="kokoro",
        kokoro_base_url="http://kokoro",
        kokoro_path="/v1/synthesize",
        xtts_base_url="http://xtts",
        xtts_path="/api/tts",
        timeout_seconds=5,
    )
    with patch("app.services.tts_service.httpx.AsyncClient", return_value=_FakeAsyncClient(get_response=_FakeResponse(status_code=200))):
        assert asyncio.run(service.health()) is True


def test_tts_synthesize_returns_audio_bytes() -> None:
    service = TTSService(
        provider="kokoro",
        kokoro_base_url="http://kokoro",
        kokoro_path="/v1/synthesize",
        xtts_base_url="http://xtts",
        xtts_path="/api/tts",
        timeout_seconds=5,
    )
    with patch(
        "app.services.tts_service.httpx.AsyncClient",
        return_value=_FakeAsyncClient(
            post_response=_FakeResponse(
                status_code=200,
                content=b"RIFFDATA",
                headers={"content-type": "audio/wav"},
            )
        ),
    ):
        result = asyncio.run(
            service.synthesize(
                text="hello",
                speaker_name="Panel Chair",
                voice_id="voice-a",
                accent="en-gb",
                tone="formal",
                speaking_style="structured",
            )
        )
    assert result.audio_bytes == b"RIFFDATA"
    assert result.media_type == "audio/wav"


def test_tts_synthesize_raises_for_unreachable_provider() -> None:
    service = TTSService(
        provider="xtts",
        kokoro_base_url="http://kokoro",
        kokoro_path="/v1/synthesize",
        xtts_base_url="http://xtts",
        xtts_path="/api/tts",
        timeout_seconds=5,
    )
    with patch(
        "app.services.tts_service.httpx.AsyncClient",
        return_value=_FakeAsyncClient(post_exc=httpx.ConnectError("down")),
    ), pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            service.synthesize(
                text="hello",
                speaker_name="Panel Chair",
                voice_id=None,
                accent=None,
                tone=None,
                speaking_style=None,
            )
        )
    assert exc_info.value.status_code == 503
