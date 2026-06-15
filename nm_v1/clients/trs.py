"""Async client for tips-results-service (TRS).

Public, no auth. Provides aggregated tip-type ROI (AI_BEST / DANGER / VALUE)
over single days or ranges. The only rollup source we currently have as
JSON — everything else needs a backend addition.
"""
from __future__ import annotations

import httpx

TRS_BASE_URL = "https://tips-results-service.onrender.com"


class TRSError(Exception):
    pass


async def fetch_stats_range(from_date: str, to_date: str) -> dict:
    url = f"{TRS_BASE_URL}/stats/range"
    params = {"from": from_date, "to": to_date}

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(url, params=params)
        except httpx.HTTPError as exc:
            raise TRSError(f"TRS request failed: {exc}") from exc

    if resp.status_code >= 400:
        raise TRSError(f"TRS returned {resp.status_code}")
    try:
        return resp.json()
    except ValueError as exc:
        raise TRSError("Invalid JSON from TRS") from exc
