"""Thin async client for racing-db /api/v1/sale*/ endpoints.

Powers the No Mugs Research → Sales subsection (Sharp tier). Each helper
returns the raw list/dict from racing-db; Pydantic validation happens at
the route layer.
"""
from __future__ import annotations

import httpx

from nm_v1.config import settings

# Sales queries can be slow on cold start. Keep above the default 10s.
_SALES_TIMEOUT = 30.0


class SalesError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


async def _get(path: str, params: dict | None = None):
    base = settings.RACING_DB_BASE_URL.rstrip("/")
    url = f"{base}/{path.lstrip('/')}"
    async with httpx.AsyncClient(timeout=_SALES_TIMEOUT) as client:
        try:
            resp = await client.get(url, params=params or {})
        except httpx.HTTPError as exc:
            raise SalesError(f"racing-db sales request failed: {exc}") from exc
    if resp.status_code == 404:
        raise SalesError("Not found", status_code=404)
    if resp.status_code >= 400:
        raise SalesError(
            f"racing-db sales returned {resp.status_code}",
            status_code=resp.status_code,
        )
    try:
        return resp.json()
    except ValueError as exc:
        raise SalesError("Invalid JSON from racing-db sales") from exc


async def list_sales(
    house: str | None = None,
    year: int | None = None,
    sale_type: str | None = None,
    limit: int = 100,
) -> list[dict]:
    params: dict = {"limit": limit}
    if house: params["house"] = house
    if year: params["year"] = year
    if sale_type: params["sale_type"] = sale_type
    data = await _get("/api/v1/sales", params)
    return data if isinstance(data, list) else []


async def get_sale(sale_code: str) -> dict:
    data = await _get(f"/api/v1/sale/{sale_code}")
    return data if isinstance(data, dict) else {}


async def list_sale_lots(
    sale_code: str,
    limit: int = 100,
    offset: int = 0,
    status: str | None = None,
    tier: str | None = None,
) -> list[dict]:
    params: dict = {"limit": limit, "offset": offset}
    if status: params["status"] = status
    if tier: params["tier"] = tier
    data = await _get(f"/api/v1/sale/{sale_code}/lots", params)
    return data if isinstance(data, list) else []
