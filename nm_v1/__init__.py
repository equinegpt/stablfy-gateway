"""No Mugs Punting API surface (v1).

Lifted wholesale from the standalone `no-mugs-gateway` repo: aggregator
endpoints that compose stablfy-social, RA Crawler, racing-db, PF and TRS into
single responses shaped for the NO MUGS iOS app.

Mounted from `gateway.py` via:

    from nm_v1 import build_router
    app.include_router(build_router(), dependencies=[Depends(verify_app_token)])

All routes carry their own `/v1` prefix from inside each sub-router, so the
parent include passes no prefix.
"""
from fastapi import APIRouter

from nm_v1.routes import (
    agreements,
    ask,
    build,
    horses,
    mugs,
    races,
    rank,
    roi,
    sectionals,
    today,
)


def build_router() -> APIRouter:
    """Return one combined router containing every No Mugs `/v1/*` route."""
    router = APIRouter()
    router.include_router(today.router)
    router.include_router(races.router)
    router.include_router(horses.router)
    router.include_router(ask.router)
    router.include_router(build.router)
    router.include_router(mugs.router)
    router.include_router(agreements.router)
    router.include_router(rank.router)
    router.include_router(sectionals.router)
    router.include_router(roi.router)
    return router
