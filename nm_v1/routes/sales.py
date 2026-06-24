"""Sales catalogues + parade biomech browser — Research → Sales (Sharp tier).

Three thin proxies onto racing-db's /api/v1/sale*/ surface:
  - GET /v1/sales            (catalogue index, filterable by house/year/type)
  - GET /v1/sale/{code}      (catalogue detail)
  - GET /v1/sale/{code}/lots (paginated lots with biomech tier joined in)

The biomech tier filter on `/lots?tier=TOP` is the No Mugs Sharp hook —
nobody else surfaces parade biomechanics next to live sale prices.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from nm_v1.clients.racing_db_sales import (
    SalesError,
    get_sale,
    list_sale_lots,
    list_sales,
)
from nm_v1.models import SaleDetail, SaleLot, SaleSummary

router = APIRouter(prefix="/v1", tags=["sales"])


@router.get("/sales", response_model=list[SaleSummary])
async def sales_index(
    house: str | None = Query(None, description="MM | INGLIS | NZB"),
    year: int | None = Query(None, ge=1990, le=2100),
    sale_type: str | None = Query(None, description="Yearling | Weanling | R2R | Broodmare"),
    limit: int = Query(100, ge=1, le=500),
):
    try:
        rows = await list_sales(house=house, year=year, sale_type=sale_type, limit=limit)
    except SalesError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return [SaleSummary(**r) for r in rows]


@router.get("/sale/{sale_code}", response_model=SaleDetail)
async def sale_detail(sale_code: str):
    try:
        data = await get_sale(sale_code)
    except SalesError as exc:
        status = exc.status_code if exc.status_code else 502
        raise HTTPException(status_code=status, detail=str(exc))
    if not data:
        raise HTTPException(status_code=404, detail=f"Sale {sale_code} not found")
    return SaleDetail(**data)


@router.get("/sale/{sale_code}/lots", response_model=list[SaleLot])
async def sale_lots(
    sale_code: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None, description="sold | passed_in | withdrawn"),
    tier: str | None = Query(None, description="TOP | MID | BOT"),
):
    try:
        rows = await list_sale_lots(
            sale_code, limit=limit, offset=offset, status=status, tier=tier,
        )
    except SalesError as exc:
        status_code = exc.status_code if exc.status_code else 502
        raise HTTPException(status_code=status_code, detail=str(exc))
    return [SaleLot(**r) for r in rows]
