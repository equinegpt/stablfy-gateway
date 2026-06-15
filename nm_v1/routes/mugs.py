"""Tab 1 — Mugs.

Reuse-first: today's picks come from `/api/curated`. Per-lane rolling SR / ROI
come from scraping `/best-of-day` HTML (no JSON source yet). Race times come
from RA Crawler. All upstreams are best-effort — a slow scrape or a missing
RA Crawler row doesn't break the picks list.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query

from nm_v1.clients.ra_crawler import RACrawlerError, fetch_races
from nm_v1.clients.stablfy_social import (
    UpstreamError,
    UpstreamNotFound,
    fetch_best_of_day_html,
    fetch_curated,
)
from nm_v1.models import MugsResponse
from nm_v1.services.bod_summary import parse_bod_summaries
from nm_v1.services.mugs_today import build_today

router = APIRouter(prefix="/v1", tags=["mugs"])


@router.get("/mugs", response_model=MugsResponse)
async def get_mugs(
    date: str | None = Query(default=None),
    days: int = Query(default=30, ge=1, le=365),
):
    try:
        curated = await fetch_curated(date)
    except UpstreamNotFound:
        raise HTTPException(status_code=404, detail="No curated picks for that date")
    except UpstreamError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    # Race times + BoD summary scrape in parallel — both are best-effort.
    races_task = asyncio.create_task(_safe_fetch_races(date))
    summary_task = asyncio.create_task(_safe_scrape_bod(days))
    ra_races = await races_task
    bod_summaries = await summary_task

    return build_today(curated, ra_races, bod_summaries=bod_summaries, days=days)


async def _safe_fetch_races(date: str | None) -> list[dict]:
    try:
        return await fetch_races(date)
    except RACrawlerError:
        return []


async def _safe_scrape_bod(days: int) -> dict:
    try:
        html = await fetch_best_of_day_html(days)
    except UpstreamError:
        return {}
    try:
        return parse_bod_summaries(html)
    except Exception:
        return {}
