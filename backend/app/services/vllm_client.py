from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx


class InferenceError(RuntimeError):
    pass


class VLLMClient:
    def __init__(self, base_url: str, timeout_seconds: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout_seconds

    async def ping(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.base_url}/v1/models")
                return response.status_code < 500
        except Exception:
            return False

    async def list_model_refs(self) -> set[str]:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{self.base_url}/v1/models")
                response.raise_for_status()
        except Exception:
            return set()

        payload = response.json()
        models = payload.get("data", [])
        refs: set[str] = set()
        for item in models:
            id_ = item.get("id")
            if isinstance(id_, str) and id_:
                refs.add(id_)
        return refs

    async def chat(
        self,
        *,
        model_ref: str,
        messages: list[dict[str, Any]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model_ref,
            "messages": messages,
            "stream": False,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.base_url}/v1/chat/completions", json=payload)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise TimeoutError("vLLM request timed out") from exc
        except httpx.HTTPStatusError as exc:
            raise InferenceError(exc.response.text) from exc
        except httpx.HTTPError as exc:
            raise InferenceError(str(exc)) from exc

        return response.json()

    async def stream_chat(
        self,
        *,
        model_ref: str,
        messages: list[dict[str, Any]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        payload: dict[str, Any] = {
            "model": model_ref,
            "messages": messages,
            "stream": True,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", f"{self.base_url}/v1/chat/completions", json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        if line.startswith("data: "):
                            data = line[6:]
                            if data.strip() == "[DONE]":
                                break
                            try:
                                yield json.loads(data)
                            except json.JSONDecodeError as exc:
                                raise InferenceError(f"Invalid stream payload: {line}") from exc
        except httpx.TimeoutException as exc:
            raise TimeoutError("vLLM stream timed out") from exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response is not None else "unknown"
            raise InferenceError(f"vLLM stream HTTP error: status={status_code}") from exc
        except httpx.HTTPError as exc:
            raise InferenceError(str(exc)) from exc
