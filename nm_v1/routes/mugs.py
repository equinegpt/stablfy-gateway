"""Tab 1 — Mugs. Best of Day + production lane library.

Reuse-first: today's picks come from /api/curated (no auth) and race
times come from RA Crawler. Both upstreams are best-effort — a missing
RA Crawler row just leaves race_time null on the pick.

The old per-lane SR/ROI HTML scrape of /best-of-day was dropped on
2026-06-30 when stablfy-social locked in the L1/L2/L3/L4 lane system —
audit numbers are now hard-coded in mugs_today.py from the 9-week
audit (Apr 23 → Jun 26) and refreshed manually when that audit re-runs.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query

from nm_v1.clients.ra_crawler import RACrawlerError, fetch_races
from nm_v1.clients.stablfy_social import (
    UpstreamError,
    UpstreamNotFound,
    fetch_curated,
)
from nm_v1.models import MugsResponse
from nm_v1.services.mugs_today import build_today

router = APIRouter(prefix="/v1", tags=["mugs"])


@router.get("/mugs", response_model=MugsResponse)
async def get_mugs(
    date: str | None = Query(default=None),
):
    try:
        curated = await fetch_curated(date)
    except UpstreamNotFound:
        raise HTTPException(status_code=404, detail="No curated picks for that date")
    except UpstreamError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    ra_races = await _safe_fetch_races(date)
    return build_today(curated, ra_races)


async def _safe_fetch_races(date: str | None) -> list[dict]:
    try:
        return await fetch_races(date)
    except RACrawlerError:
        return []
