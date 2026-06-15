"""Tab 2 — AI Agreement.

Pulls today's /picks full_card from stablfy-social, computes 3-voice
convergence (Clone + Gemini + SkyNet), joins race times from RA Crawler.
No new upstream endpoints — reuse-first.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from nm_v1.clients.ra_crawler import RACrawlerError, fetch_races
from nm_v1.clients.stablfy_social import (
    UpstreamError,
    UpstreamNotFound,
    fetch_picks,
)
from nm_v1.models import AgreementsResponse
from nm_v1.services.agreements import build_agreements

router = APIRouter(prefix="/v1", tags=["agreements"])


@router.get("/agreements", response_model=AgreementsResponse)
async def get_agreements(date: str | None = Query(default=None)):
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

    return build_agreements(picks, ra_races)
