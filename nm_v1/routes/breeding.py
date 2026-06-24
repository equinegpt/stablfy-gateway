"""Breeding analytics — racing-db proxies for the No Mugs Research tab.

All five `/v1/breeding/*` routes are thin proxies. racing-db owns the
materialised views (mv_sire_leaderboard, mv_breeding_distance_dna, etc.)
so each query lands in sub-second.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from nm_v1.clients.racing_db_breeding import (
    BreedingError,
    fetch_class_ceiling,
    fetch_distance_dna,
    fetch_nicks,
    fetch_sire_leaderboard,
    fetch_sire_sectionals,
)
from nm_v1.models import (
    ClassCeilingRow,
    DistanceDNARow,
    NickRow,
    SireLeaderboardRow,
    SireSectionalRow,
)

router = APIRouter(prefix="/v1/breeding", tags=["breeding"])


@router.get("/sire-leaderboard", response_model=list[SireLeaderboardRow])
async def sire_leaderboard(
    limit: int = Query(50, ge=1, le=200),
    min_runners: int = Query(10, ge=1),
    sort: str = Query("prizemoney"),
):
    try:
        rows = await fetch_sire_leaderboard(limit=limit, min_runners=min_runners, sort=sort)
    except BreedingError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return [SireLeaderboardRow(**r) for r in rows]


@router.get("/distance-dna", response_model=list[DistanceDNARow])
async def distance_dna(
    limit: int = Query(50, ge=1, le=200),
    min_runners: int = Query(15, ge=1),
):
    try:
        rows = await fetch_distance_dna(limit=limit, min_runners=min_runners)
    except BreedingError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return [DistanceDNARow(**r) for r in rows]


@router.get("/nicks", response_model=list[NickRow])
async def nicks(
    limit: int = Query(50, ge=1, le=200),
    min_runners: int = Query(2, ge=1),
):
    try:
        rows = await fetch_nicks(limit=limit, min_runners=min_runners)
    except BreedingError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return [NickRow(**r) for r in rows]


@router.get("/sectionals", response_model=list[SireSectionalRow])
async def sire_sectionals(
    limit: int = Query(50, ge=1, le=200),
    min_runs: int = Query(50, ge=1),
):
    try:
        rows = await fetch_sire_sectionals(limit=limit, min_runs=min_runs)
    except BreedingError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return [SireSectionalRow(**r) for r in rows]


@router.get("/class-ceiling", response_model=list[ClassCeilingRow])
async def class_ceiling(
    limit: int = Query(50, ge=1, le=200),
    min_runners: int = Query(15, ge=1),
):
    try:
        rows = await fetch_class_ceiling(limit=limit, min_runners=min_runners)
    except BreedingError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return [ClassCeilingRow(**r) for r in rows]
