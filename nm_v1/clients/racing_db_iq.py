"""Async client for racing-db /api/iq/* (race intelligence).

Powers the No Mugs Research → Planner subsection (Sharp tier). The upstream
endpoint pulls live upcoming races from ra-crawler and overlays winning
rating benchmarks from mv_iq_winning_runs — so a single request returns
race cards plus a "this rating is competitive here" verdict per race.
"""
from __future__ import annotations

import httpx

from nm_v1.config import settings

# Upstream chains ra-crawler + mv_iq_winning_runs joins; allow generous
# headroom for the Render cold start path.
_IQ_TIMEOUT = 45.0


class IQError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


async def fetch_upcoming(params: dict) -> dict:
    """Pass-through to racing-db /api/iq/upcoming. Caller supplies the
    full query-param dict so this client doesn't need to know every filter
    racing-db supports today (or adds tomorrow).
    """
    base = settings.RACING_DB_BASE_URL.rstrip("/")
    url = f"{base}/api/iq/upcoming"
    async with httpx.AsyncClient(timeout=_IQ_TIMEOUT) as client:
        try:
            resp = await client.get(url, params=params)
        except httpx.HTTPError as exc:
            raise IQError(f"racing-db iq request failed: {exc}") from exc
    if resp.status_code >= 400:
        raise IQError(
            f"racing-db iq returned {resp.status_code}",
            status_code=resp.status_code,
        )
    try:
        data = resp.json()
    except ValueError as exc:
        raise IQError("Invalid JSON from racing-db iq") from exc
    return data if isinstance(data, dict) else {}
