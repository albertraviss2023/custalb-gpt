from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx


class InferenceError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, base_url: str, timeout_seconds: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout_seconds

    async def ping(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                return response.status_code < 500
        except Exception:
            return False

    async def chat(
        self,
        *,
        model_ref: str,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model_ref,
            "messages": messages,
            "stream": False,
        }
        options: dict[str, Any] = {}
        if temperature is not None:
            options["temperature"] = temperature
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        if options:
            payload["options"] = options

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise TimeoutError("Inference request timed out") from exc
        except httpx.HTTPStatusError as exc:
            raise InferenceError(exc.response.text) from exc
        except httpx.HTTPError as exc:
            raise InferenceError(str(exc)) from exc

        return response.json()

    async def stream_chat(
        self,
        *,
        model_ref: str,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        payload: dict[str, Any] = {
            "model": model_ref,
            "messages": messages,
            "stream": True,
        }
        options: dict[str, Any] = {}
        if temperature is not None:
            options["temperature"] = temperature
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        if options:
            payload["options"] = options

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError as exc:
                            raise InferenceError(f"Invalid stream payload: {line}") from exc
        except httpx.TimeoutException as exc:
            raise TimeoutError("Inference stream timed out") from exc
        except httpx.HTTPStatusError as exc:
            raise InferenceError(exc.response.text) from exc
        except httpx.HTTPError as exc:
            raise InferenceError(str(exc)) from exc