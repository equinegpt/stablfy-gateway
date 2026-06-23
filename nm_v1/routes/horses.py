from fastapi import APIRouter, HTTPException, Query

from nm_v1.clients.racing_db import RacingDBError, get_horse_record, search_horses
from nm_v1.models import HorseDeepDive, HorseSearchResult
from nm_v1.services.horse import build_deep_dive, pick_best_match

router = APIRouter(prefix="/v1", tags=["horses"])


@router.get("/horse/search", response_model=list[HorseSearchResult])
async def search_horse(
    q: str = Query(..., min_length=2),
    limit: int = Query(8, ge=1, le=20),
):
    """Horse name search for the in-app search bar.

    Top matches by prizemoney across the racing-db horses table. Used by the
    NO MUGS Horse Search sheet — tapping a result then opens the rich
    `/v1/horse?name=...` profile.
    """
    try:
        results = await search_horses(q, limit=limit)
    except RacingDBError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return [HorseSearchResult(**r) for r in results]


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
