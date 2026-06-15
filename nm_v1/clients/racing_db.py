"""Async client for the racing-db read-only JSON API (horse deep-dive)."""
from __future__ import annotations

import httpx

from nm_v1.config import settings


class RacingDBError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


async def _get(path: str, params: dict | None = None, timeout: float | None = None) -> dict | list:
    base = settings.RACING_DB_BASE_URL.rstrip("/")
    url = f"{base}/{path.lstrip('/')}"
    t = timeout if timeout is not None else settings.UPSTREAM_TIMEOUT_SECONDS
    async with httpx.AsyncClient(timeout=t) as client:
        try:
            resp = await client.get(url, params=params or {})
        except httpx.HTTPError as exc:
            raise RacingDBError(f"racing-db request failed: {exc}") from exc
    if resp.status_code >= 400:
        raise RacingDBError(f"racing-db returned {resp.status_code}", status_code=resp.status_code)
    try:
        return resp.json()
    except ValueError as exc:
        raise RacingDBError("Invalid JSON from racing-db") from exc


async def search_horses(name: str, limit: int = 5) -> list[dict]:
    result = await _get("/api/search/horses", {"q": name, "limit": limit})
    return result if isinstance(result, list) else []


async def get_horse_record(horse_code: str, form_limit: int = 10) -> dict:
    # The v1 profile endpoint joins career/jockey/trainer stats — it routinely
    # takes 10-20s on cold connections, so we override the default timeout.
    result = await _get(
        f"/api/v1/horse/{horse_code}",
        {"form_limit": form_limit},
        timeout=30.0,
    )
    return result if isinstance(result, dict) else {}
