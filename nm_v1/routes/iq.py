"""Race IQ — Research → Planner (Sharp tier).

Forward-looking race card with class+distance winning-rating benchmarks and
an optional "given my rating, is this race winnable" verdict.
"""
from __future__ import annotations

from datetime import date as _date, timedelta

from fastapi import APIRouter, HTTPException, Query

from nm_v1.clients.racing_db_iq import IQError, fetch_upcoming
from nm_v1.models import UpcomingRacesResponse

router = APIRouter(prefix="/v1/iq", tags=["iq"])


@router.get("/upcoming", response_model=UpcomingRacesResponse)
async def upcoming_races(
    from_date: str | None = Query(None, description="YYYY-MM-DD; defaults to today"),
    to_date: str | None = Query(None, description="YYYY-MM-DD; defaults to from_date+1"),
    rating: int | None = Query(None, ge=0, le=140, description="Overlay competitiveness for this rating"),
    states: str | None = Query(None, description="Comma-separated, e.g. NSW,VIC,QLD"),
    types: str | None = Query(None, description="Comma-separated: M(etro), P(rovincial), C(ountry)"),
    maidens: bool | None = Query(None),
    bonus_only: bool | None = Query(None),
    min_prize: int | None = Query(None, ge=0),
    min_dist: int | None = Query(None, ge=800, le=4000),
    max_dist: int | None = Query(None, ge=800, le=4000),
):
    """Today/tomorrow race card with winning-rating overlay.

    Pass `rating=75` (etc.) to colour each race STRONG / POSSIBLE /
    OVERQUALIFIED / UNLIKELY based on the historical winning-rating
    distribution for that class+distance bucket.
    """
    # Default window: today through tomorrow.
    today = _date.today()
    fd = from_date or today.isoformat()
    td = to_date or (today + timedelta(days=1)).isoformat()

    params: dict = {"from_date": fd, "to_date": td}
    if rating is not None: params["rating"] = rating
    if states: params["states"] = states
    if types: params["types"] = types
    if maidens is not None: params["maidens"] = str(maidens).lower()
    if bonus_only is not None: params["bonus_only"] = str(bonus_only).lower()
    if min_prize is not None: params["min_prize"] = min_prize
    if min_dist is not None: params["min_dist"] = min_dist
    if max_dist is not None: params["max_dist"] = max_dist

    try:
        data = await fetch_upcoming(params)
    except IQError as exc:
        status = exc.status_code if exc.status_code else 502
        raise HTTPException(status_code=status, detail=str(exc))
    return UpcomingRacesResponse(**data)
