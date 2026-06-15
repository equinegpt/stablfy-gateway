"""Tab 6 — ROI. Window-rolled system stats proxied from TRS."""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query

from nm_v1.clients.trs import TRSError, fetch_stats_range
from nm_v1.models import SystemsROIResponse
from nm_v1.services.roi import build_systems

router = APIRouter(prefix="/v1", tags=["roi"])

MELBOURNE = ZoneInfo("Australia/Melbourne")


@router.get("/roi/systems", response_model=SystemsROIResponse)
async def get_system_rois(days: int = Query(default=30, ge=1, le=365)):
    today = datetime.now(MELBOURNE).date()
    from_date = (today - timedelta(days=days - 1)).isoformat()
    to_date = today.isoformat()
    try:
        payload = await fetch_stats_range(from_date, to_date)
    except TRSError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return build_systems(payload)
