from fastapi import APIRouter, HTTPException, Query

from nm_v1.clients.racing_db import RacingDBError, get_horse_record, search_horses
from nm_v1.models import HorseDeepDive
from nm_v1.services.horse import build_deep_dive, pick_best_match

router = APIRouter(prefix="/v1", tags=["horses"])


@router.get("/horse", response_model=HorseDeepDive)
async def get_horse(name: str = Query(..., min_length=2)):
    try:
        candidates = await search_horses(name)
    except RacingDBError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    match = pick_best_match(name, candidates)
    if match is None or not match.get("horse_code"):
        raise HTTPException(status_code=404, detail="Horse not found")

    try:
        record = await get_horse_record(str(match["horse_code"]))
    except RacingDBError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    deep_dive = build_deep_dive(record)
    if deep_dive is None:
        raise HTTPException(status_code=404, detail="Horse record unavailable")
    return deep_dive
