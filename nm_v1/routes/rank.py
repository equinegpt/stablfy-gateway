"""Tab 3 — Rank (top 3 by Clone rank per race).

Reuses /picks (stablfy-social) + RA Crawler /races. No new upstream endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from nm_v1.clients.ra_crawler import RACrawlerError, fetch_races
from nm_v1.clients.stablfy_social import (
    UpstreamError,
    UpstreamNotFound,
    fetch_picks,
)
from nm_v1.models import RankResponse
from nm_v1.services.rank import build_rank

router = APIRouter(prefix="/v1", tags=["rank"])


@router.get("/rank", response_model=RankResponse)
async def get_rank(date: str | None = Query(default=None)):
    try:
        picks = await fetch_picks(date)
    except UpstreamNotFound:
        raise HTTPException(status_code=404, detail="No picks for that date")
    except UpstreamError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    ra_races: list[dict] = []
    try:
        ra_races = await fetch_races(date)
    except RACrawlerError:
        ra_races = []

    return build_rank(picks, ra_races)
