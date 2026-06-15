from fastapi import APIRouter, HTTPException, Query

from nm_v1.clients.stablfy_social import (
    UpstreamError,
    UpstreamNotFound,
    fetch_picks,
)
from nm_v1.models import TodayMugsResponse
from nm_v1.services.mugs import build_response

router = APIRouter(prefix="/v1/today", tags=["today"])


@router.get("/mugs", response_model=TodayMugsResponse)
async def get_today_mugs(date: str | None = Query(default=None)):
    try:
        picks = await fetch_picks(date)
    except UpstreamNotFound:
        raise HTTPException(status_code=404, detail="No picks available for date")
    except UpstreamError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return build_response(picks)
