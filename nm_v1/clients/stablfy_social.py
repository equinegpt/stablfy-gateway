"""Thin async client for the upstream stablfy-social /picks endpoint."""
from __future__ import annotations

import httpx

from nm_v1.config import settings


class UpstreamError(Exception):
    """Raised when the upstream call fails for a reason worth surfacing."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class UpstreamNotFound(UpstreamError):
    """Upstream returned 404 — no picks for the requested date."""


async def fetch_curated(date: str | None = None) -> dict:
    """Fetch /api/curated — today's curated paper-trade snapshot.

    Public, no auth. Returns `best_of_day[]`, `lanes.{L4_class, L2_mid_favs,
    L1_short_favs, L3_maiden, V_value, P_divergence, S_steam}`,
    `is_stakes_day`, `metro_pick_count`, etc.
    """
    base = settings.STABLFY_SOCIAL_BASE_URL.rstrip("/")
    url = f"{base}/api/curated"
    params = {"date": date} if date else {}

    async with httpx.AsyncClient(timeout=settings.UPSTREAM_TIMEOUT_SECONDS) as client:
        try:
            resp = await client.get(url, params=params)
        except httpx.HTTPError as exc:
            raise UpstreamError(f"stablfy-social /api/curated failed: {exc}") from exc

        if resp.status_code == 404:
            raise UpstreamNotFound("No curated picks for that date", status_code=404)
        if resp.status_code >= 400:
            raise UpstreamError(
                f"stablfy-social returned {resp.status_code}",
                status_code=resp.status_code,
            )
        return resp.json()


async def fetch_picks(date: str | None = None) -> dict:
    base = settings.STABLFY_SOCIAL_BASE_URL.rstrip("/")
    url = f"{base}/picks"
    params = {"date": date} if date else {}
    headers = {"X-Api-Key": settings.STABLFY_PICKS_API_KEY}

    async with httpx.AsyncClient(timeout=settings.UPSTREAM_TIMEOUT_SECONDS) as client:
        try:
            resp = await client.get(url, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise UpstreamError(f"stablfy-social request failed: {exc}") from exc

        if resp.status_code == 404:
            raise UpstreamNotFound("No picks available for date", status_code=404)
        if resp.status_code >= 400:
            raise UpstreamError(
                f"stablfy-social returned {resp.status_code}",
                status_code=resp.status_code,
            )
        return resp.json()
