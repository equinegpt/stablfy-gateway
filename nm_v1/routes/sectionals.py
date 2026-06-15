"""Tab 5 — Sectionals.

Two GET routes:
  • /v1/sectionals/races?date=YYYY-MM-DD  — meetings → races index for the
    date picker. Sourced from RA Crawler /races. No PF call here.
  • The per-race sectional payload reuses the existing
    `/v1/race/{race_id}/sectionals` route — that endpoint now returns the full
    `runs[]` history per runner plus averages (additive, backwards-compat for
    the Race Detail view).
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query

from nm_v1.clients.ra_crawler import RACrawlerError, fetch_races
from nm_v1.models import SectionalRacesResponse
from nm_v1.services.sectional_index import build_sectional_meetings

router = APIRouter(prefix="/v1", tags=["sectionals"])

MELBOURNE = ZoneInfo("Australia/Melbourne")


@router.get("/sectionals/races", response_model=SectionalRacesResponse)
async def get_sectional_races(date: str | None = Query(default=None)):
    target_date = date or datetime.now(MELBOURNE).date().isoformat()
    try:
        races = await fetch_races(target_date)
    except RACrawlerError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return build_sectional_meetings(races, target_date)
