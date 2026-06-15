from fastapi import APIRouter, HTTPException, Query

from nm_v1.clients.punting_form import PFError, fetch_ireel, fetch_speedmap
from nm_v1.clients.stablfy_social import (
    UpstreamError,
    UpstreamNotFound,
    fetch_picks,
)
from nm_v1.models import RaceDetail, RacesIndexResponse, RaceSectionals, RaceSpeedmap
from nm_v1.services.races import build_race_detail, build_races_index
from nm_v1.services.sectionals import build_sectionals
from nm_v1.services.speedmap import build_speedmap
from nm_v1.services.voices import parse_race_id

router = APIRouter(prefix="/v1", tags=["races"])


async def _fetch(date: str | None) -> dict:
    try:
        return await fetch_picks(date)
    except UpstreamNotFound:
        raise HTTPException(status_code=404, detail="No races available for date")
    except UpstreamError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/races", response_model=RacesIndexResponse)
async def get_races(date: str | None = Query(default=None)):
    picks = await _fetch(date)
    return build_races_index(picks)


@router.get("/race/{race_id}", response_model=RaceDetail)
async def get_race(race_id: str, date: str | None = Query(default=None)):
    picks = await _fetch(date)
    detail = build_race_detail(picks, race_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Race not found")
    return detail


@router.get("/race/{race_id}/speedmap", response_model=RaceSpeedmap)
async def get_speedmap(race_id: str):
    parsed = parse_race_id(race_id)
    if parsed is None:
        raise HTTPException(status_code=400, detail="race_id has no PF meeting id")
    try:
        payload = await fetch_speedmap(*parsed)
    except PFError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    speedmap = build_speedmap(payload, race_id)
    if speedmap is None:
        raise HTTPException(status_code=404, detail="No speed map for this race")
    return speedmap


@router.get("/race/{race_id}/sectionals", response_model=RaceSectionals)
async def get_sectionals(race_id: str):
    parsed = parse_race_id(race_id)
    if parsed is None:
        raise HTTPException(status_code=400, detail="race_id has no PF meeting id")
    try:
        payload = await fetch_ireel(*parsed)
    except PFError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    sectionals = build_sectionals(payload, race_id)
    if sectionals is None:
        raise HTTPException(status_code=404, detail="No sectionals for this race")
    return sectionals
