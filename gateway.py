from __future__ import annotations

import os
from typing import Optional, Dict, Any, List
import datetime as dt          # 👈 add this

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
# ---- SkyNet proxy (PuntingForm → app-safe shape) ----

class SkynetPricesRequest(BaseModel):
    # Body the app sends: { "date": "YYYY-MM-DD" }
    date: str


class SkynetPrice(BaseModel):
    # Shape the app expects (SkynetRow in Swift)
    meetingId: Optional[int] = None
    track: Optional[str] = None
    raceNumber: int
    tabNumber: int
    horse: Optional[str] = None
    price: Optional[float] = None          # AI fair price
    tabCurrentPrice: Optional[float] = None  # TAB price
    rank: Optional[int] = None             # optional for now


def _pf_date_variants(iso_date: str) -> list[str]:
    """
    Turn '2025-12-05' into ['05-dec-2025', '05-Dec-2025'] so we match
    PuntingForm's `meetingDate` expectations.
    """
    try:
        d = dt.date.fromisoformat(iso_date)
    except ValueError:
        # If it's already in some dd-mmm-yyyy shape, just try as-is
        return [iso_date]

    base = d.strftime("%d-%b-%Y")  # 05-Dec-2025
    parts = base.split("-")
    if len(parts) == 3:
        lower = f"{parts[0]}-{parts[1].lower()}-{parts[2]}"  # 05-dec-2025
    else:
        lower = base.lower()
    return [lower, base]


@app.post(
    "/skynet/prices",
    response_model=list[SkynetPrice],
    dependencies=[Depends(verify_app_token)],
)
async def proxy_skynet_prices(req: SkynetPricesRequest):
    """
    App → Gateway:

        POST /skynet/prices
        { "date": "YYYY-MM-DD" }

    Gateway → PuntingForm:

        GET SKYNET_BASE_URL?meetingDate=dd-mmm-yyyy&apikey=...

    Then we remap PF rows into the SkynetPrice shape the app expects.
    """
    if not SKYNET_BASE_URL or not SKYNET_API_KEY:
        raise HTTPException(status_code=500, detail="SkyNet not configured")

    last_err: Optional[str] = None

    async with httpx.AsyncClient(timeout=20.0) as client:
        for pf_date in _pf_date_variants(req.date):
            params = {"meetingDate": pf_date, "apikey": SKYNET_API_KEY}

            try:
                resp = await client.get(SKYNET_BASE_URL, params=params)
            except httpx.RequestError as exc:
                # This is the bit currently biting us – log *everything*
                print(
                    f"[GW SKYNET] RequestError url={SKYNET_BASE_URL} "
                    f"params={params} exc={repr(exc)}"
                )
                last_err = f"request error: {repr(exc)}"
                continue

            print(
                f"[GW SKYNET] GET {resp.url} status={resp.status_code} "
                f"bytes={len(resp.content)}"
            )

            if resp.status_code >= 400:
                last_err = f"http {resp.status_code}: {resp.text[:200]}"
                continue

            try:
                data = resp.json()
            except ValueError as exc:
                last_err = f"json error: {repr(exc)}"
                continue

            if not isinstance(data, list):
                last_err = f"unexpected payload type: {type(data)}"
                continue

            out: list[SkynetPrice] = []

            for item in data:
                if not isinstance(item, dict):
                    continue

                try:
                    race_no = int(item.get("raceNo"))
                    tab_no = int(item.get("tabNo"))
                except (TypeError, ValueError):
                    continue

                out.append(
                    SkynetPrice(
                        track=item.get("venue"),
                        raceNumber=race_no,
                        tabNumber=tab_no,
                        horse=item.get("horse"),
                        price=item.get("aiPrice"),
                        tabCurrentPrice=item.get("tabPrice"),
                    )
                )

            # ✅ First variant that worked
            return out

    # If we get here, both date variants failed
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
