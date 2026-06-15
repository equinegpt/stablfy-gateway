"""Async client for Stable Brain's /api/ask (NL system builder)."""
from __future__ import annotations

import httpx

from nm_v1.config import settings


class StableBrainError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class StableBrainNotConfigured(StableBrainError):
    pass


async def ask_system(query: str) -> dict:
    if not settings.STABLE_BRAIN_API_KEY:
        raise StableBrainNotConfigured("STABLE_BRAIN_API_KEY not configured", status_code=503)

    url = f"{settings.STABLE_BRAIN_BASE_URL.rstrip('/')}/api/ask"
    headers = {
        "X-Api-Key": settings.STABLE_BRAIN_API_KEY,
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=settings.STABLE_BRAIN_TIMEOUT_SECONDS) as client:
        try:
            resp = await client.post(url, json={"query": query}, headers=headers)
        except httpx.HTTPError as exc:
            raise StableBrainError(f"stable-brain request failed: {exc}") from exc

    if resp.status_code >= 400:
        raise StableBrainError(
            f"stable-brain returned {resp.status_code}", status_code=resp.status_code
        )
    try:
        return resp.json()
    except ValueError as exc:
        raise StableBrainError("Invalid JSON from stable-brain") from exc
