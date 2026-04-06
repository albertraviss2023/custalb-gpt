from __future__ import annotations

from fastapi import Header, HTTPException, status

from app.core.settings import settings


async def require_api_key(authorization: str | None = Header(default=None)) -> None:
    if not settings.api_key:
        return

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )

    token = authorization.removeprefix("Bearer ").strip()
    if token != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )