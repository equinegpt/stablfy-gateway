from __future__ import annotations

import os
from typing import Optional, Dict, Any, List
import datetime as dt          # 👈 add this
from datetime import date as _date

import httpx
from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel

app = FastAPI(
    title="Stablfy Gateway",
    version="0.1.0",
)

# -------------------------------------------------------------------
# Config from environment
# -------------------------------------------------------------------

APP_TOKEN = os.getenv("APP_TOKEN", "")

IREEL_API_KEY = os.getenv("IREEL_API_KEY", "")
IREEL_BASE_URL = os.getenv("IREEL_BASE_URL", "https://api.ireel.ai/chat")

SKYNET_BASE_URL = os.getenv("SKYNET_BASE_URL", "")
SKYNET_API_KEY = os.getenv("SKYNET_API_KEY", "")

from datetime import datetime

SKYNET_PF_URL = os.getenv(
    "SKYNET_PF_URL",
    "https://puntx.puntingform.com.au/api/skynet/getskynetprices",
)

# -------------------------------------------------------------------
# Simple header auth for the app
# -------------------------------------------------------------------

async def verify_app_token(x_app_token: str = Header(...)) -> None:
    """
    Require the iOS app to send X-App-Token. Value must match APP_TOKEN.
    """
    if not APP_TOKEN:
        raise HTTPException(
            status_code=500,
            detail="Gateway APP_TOKEN not configured",
        )

    if x_app_token != APP_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid app token")


# -------------------------------------------------------------------
# Models
# -------------------------------------------------------------------

class IreelChatRequest(BaseModel):
    assistant_id: str              # e.g. "a013ab78-9dca-4329-a1eb-..."
    project_id: Optional[str] = None
    prompt: str
    context: Optional[Dict[str, Any]] = None   # meetingId, track, raceNumber, etc.


class IreelChatResponse(BaseModel):
    response: str                  # clean text for the app to use
    raw: Dict[str, Any]            # full iReel JSON if needed


class SkynetPricesRequest(BaseModel):
    # iOS sends: { "date": "2025-12-05" }
    date: str  # ISO day "YYYY-MM-DD"


class SkynetPrice(BaseModel):
    # Shape that matches SkynetService.SkynetRow on-device
    meetingId: Optional[int] = None
    track: Optional[str] = None
    raceNumber: int
    tabNumber: int
    horse: Optional[str] = None
    price: Optional[float] = None          # AI price
    tabCurrentPrice: Optional[float] = None  # TAB price
    rank: Optional[int] = None

# -------------------------------------------------------------------
# iReel proxy
# -------------------------------------------------------------------

@app.post(
    "/ireel/chat",
    response_model=IreelChatResponse,
    dependencies=[Depends(verify_app_token)],
)
async def proxy_ireel_chat(req: IreelChatRequest) -> IreelChatResponse:
    """
    Single entry point the iOS app will call instead of api.ireel.ai.
    We add the real iReel API key on the server side.
    """
    if not IREEL_API_KEY:
        raise HTTPException(status_code=500, detail="IREEL_API_KEY not configured")

    base = IREEL_BASE_URL.rstrip("/")
    url = f"{base}/{req.assistant_id}"

    params: Dict[str, Any] = {}
    if req.project_id:
        params["projectId"] = req.project_id

    headers = {
        "X-API-Key": IREEL_API_KEY,
    }

    payload: Dict[str, Any] = {"prompt": req.prompt}
    if req.context:
        payload["context"] = req.context

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, params=params, headers=headers, json=payload)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"iReel upstream error: {exc}",
        ) from exc

    # ---- DEBUG: log what iReel actually returned ----
    body_text = (resp.text or "").strip()
    print("🔎 iReel status:", resp.status_code)
    print("🔎 iReel body (first 400 chars):", body_text[:400])

    # If iReel itself returns an error code, bubble that up
    if resp.status_code >= 400:
        raise HTTPException(
            status_code=resp.status_code,
            detail=body_text or "iReel error",
        )

    # No content at all → can't JSON-decode
    if not body_text:
        raise HTTPException(
            status_code=502,
            detail="Empty response from iReel",
        )

    # Try to parse JSON; if it fails, return a clean 502 instead of crashing
    try:
        data = resp.json()
    except ValueError:
        raise HTTPException(
            status_code=502,
            detail="Invalid JSON from iReel",
        )

    return IreelChatResponse(
        response=data.get("response", "") or "",
        raw=data,
    )

# -------------------------------------------------------------------
# SkyNet proxy
# -------------------------------------------------------------------
class SkynetPricesRequest(BaseModel):
    # from the app: { "date": "2025-12-05" }
    date: str


class SkynetPrice(BaseModel):
    tabNumber: int
    price: float | None = None          # AI fair price
    tabCurrentPrice: float | None = None  # TAB price
    rank: int | None = None             # optional, if PF ever adds it


@app.post(
    "/skynet/prices",
    response_model=List[SkynetPrice],
    dependencies=[Depends(verify_app_token)],
)
async def proxy_skynet_prices(req: SkynetPricesRequest):
    """
    Fetch Skynet prices for a given day from PuntingForm and return a
    trimmed structure used by the app.

    Body from app: { "date": "YYYY-MM-DD" }.
    """
    if not SKYNET_BASE_URL:
        raise HTTPException(status_code=500, detail="SkyNet not configured")

    # Parse ISO date from the app
    try:
        d = _date.fromisoformat(req.date)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="date must be in ISO format YYYY-MM-DD",
        )

    # PF wants dd-MMM-yyyy; we try 03-dec-2025 then 03-Dec-2025
    lower = d.strftime("%d-%b-%Y").lower()
    normal = d.strftime("%d-%b-%Y")
    date_variants = [lower, normal]

    last_err: Exception | None = None

    for meeting_date in date_variants:
        params = {
            "meetingDate": meeting_date,
            "apikey": SKYNET_API_KEY or "",
        }
        print(f"[GW SKYNET] GET {SKYNET_BASE_URL} params={params}")

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=10.0, read=30.0)
            ) as client:
                resp = await client.get(SKYNET_BASE_URL, params=params)
        except httpx.RequestError as exc:
            print(
                f"[GW SKYNET] RequestError date={meeting_date} "
                f"exc={exc!r}"
            )
            last_err = exc
            continue

        if resp.status_code >= 400:
            print(
                f"[GW SKYNET] HTTP {resp.status_code} "
                f"body={resp.text[:300]}"
            )
            last_err = HTTPException(
                status_code=resp.status_code,
                detail=resp.text,
            )
            continue

        data = resp.json()
        if not isinstance(data, list):
            print(f"[GW SKYNET] Unexpected JSON shape: {type(data)}")
            last_err = RuntimeError("unexpected Skynet JSON shape")
            continue

        prices: list[SkynetPrice] = []
        for row in data:
            if not isinstance(row, dict):
                continue

            tab_no = row.get("tabNo") or row.get("tabNumber")
            if tab_no is None:
                continue

            prices.append(
                SkynetPrice(
                    tabNumber=int(tab_no),
                    price=row.get("aiPrice") or row.get("price"),
                    tabCurrentPrice=row.get("tabPrice") or row.get(
                        "tabCurrentPrice"
                    ),
                    rank=row.get("rank"),
                )
            )

        print(
            f"[GW SKYNET] OK date={meeting_date}, rows={len(prices)}"
        )
        return prices

    # If we get here, both variants failed (even with long timeout)
    raise HTTPException(
        status_code=502,
        detail=f"SkyNet upstream error: {last_err or 'no response'}",
    )

# -------------------------------------------------------------------
# Healthcheck
# -------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok"}
