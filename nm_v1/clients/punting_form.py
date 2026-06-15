"""Async client for the Punting Form API (speed maps, sectionals).

Only PF data flows through here — never bookmaker sources.
"""
from __future__ import annotations

import httpx

from nm_v1.config import settings


class PFError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


async def _get(path: str, params: dict) -> dict:
    if not settings.PF_API_KEY:
        raise PFError("PF_API_KEY not configured", status_code=500)

    base = settings.PF_API_BASE_URL.rstrip("/")
    url = f"{base}/{path.lstrip('/')}"
    params = {**params, "apiKey": settings.PF_API_KEY}

    async with httpx.AsyncClient(timeout=settings.PF_TIMEOUT_SECONDS) as client:
        try:
            resp = await client.get(url, params=params)
        except httpx.HTTPError as exc:
            raise PFError(f"PF request failed: {exc}") from exc

    if resp.status_code >= 400:
        raise PFError(f"PF returned {resp.status_code}", status_code=resp.status_code)
    try:
        return resp.json()
    except ValueError as exc:
        raise PFError("Invalid JSON from PF") from exc


async def fetch_speedmap(meeting_id: int, race_no: int) -> dict:
    return await _get("User/Speedmaps", {"meetingId": meeting_id, "raceNo": race_no})


async def fetch_ireel(meeting_id: int, race_no: int) -> dict:
    return await _get("ireel/race", {"meetingId": meeting_id, "raceNumber": race_no})
