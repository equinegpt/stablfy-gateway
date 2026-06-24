"""Thin async client for racing-db /api/breeding/* endpoints.

Powers the No Mugs Research tab (Sharp tier). Each helper returns the raw
list of dicts — typed validation happens at the route layer via Pydantic
response_model.
"""
from __future__ import annotations

import httpx

from nm_v1.config import settings

# Breeding aggregates can be slow on cold-start (Render free tier wakes the
# racing-db service). Bump above the standard upstream timeout.
_BREEDING_TIMEOUT = 30.0


class BreedingError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


async def _get(path: str, params: dict) -> list[dict]:
    base = settings.RACING_DB_BASE_URL.rstrip("/")
    url = f"{base}/{path.lstrip('/')}"
    async with httpx.AsyncClient(timeout=_BREEDING_TIMEOUT) as client:
        try:
            resp = await client.get(url, params=params)
        except httpx.HTTPError as exc:
            raise BreedingError(f"racing-db breeding request failed: {exc}") from exc
    if resp.status_code >= 400:
        raise BreedingError(
            f"racing-db breeding returned {resp.status_code}",
            status_code=resp.status_code,
        )
    try:
        data = resp.json()
    except ValueError as exc:
        raise BreedingError("Invalid JSON from racing-db breeding") from exc
    return data if isinstance(data, list) else []


async def fetch_sire_leaderboard(
    limit: int = 50,
    min_runners: int = 10,
    sort: str = "prizemoney",
) -> list[dict]:
    return await _get("/api/breeding/sire-leaderboard", {
        "limit": limit, "min_runners": min_runners, "sort": sort,
    })


async def fetch_distance_dna(limit: int = 50, min_runners: int = 15) -> list[dict]:
    return await _get("/api/breeding/distance-dna", {
        "limit": limit, "min_runners": min_runners,
    })


async def fetch_nicks(limit: int = 50, min_runners: int = 2) -> list[dict]:
    return await _get("/api/breeding/nicks", {
        "limit": limit, "min_runners": min_runners,
    })


async def fetch_sire_sectionals(limit: int = 50, min_runs: int = 50) -> list[dict]:
    return await _get("/api/breeding/sectionals", {
        "limit": limit, "min_runs": min_runs,
    })


async def fetch_class_ceiling(limit: int = 50, min_runners: int = 15) -> list[dict]:
    return await _get("/api/breeding/class-ceiling", {
        "limit": limit, "min_runners": min_runners,
    })
