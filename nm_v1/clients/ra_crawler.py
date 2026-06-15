"""Async client for the RA Crawler — race calendar with start times."""
from __future__ import annotations

import httpx

RA_CRAWLER_BASE_URL = "https://ra-crawler.onrender.com"


class RACrawlerError(Exception):
    pass


async def fetch_races(date: str | None = None) -> list[dict]:
    """Returns a list of races for a given date (today if omitted).

    Each entry has: id, race_no, date, state, track, distance_m, raceTime,
    type (C/M/P), description, class, etc. Public, no auth.
    """
    url = f"{RA_CRAWLER_BASE_URL}/races"
    params = {"date": date} if date else {}

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(url, params=params)
        except httpx.HTTPError as exc:
            raise RACrawlerError(f"RA Crawler request failed: {exc}") from exc

    if resp.status_code >= 400:
        raise RACrawlerError(f"RA Crawler returned {resp.status_code}")
    try:
        data = resp.json()
    except ValueError as exc:
        raise RACrawlerError("Invalid JSON from RA Crawler") from exc
    return data if isinstance(data, list) else []
