from __future__ import annotations

import os
from typing import Optional, Dict, Any, List

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
    meeting_id: int
    race_number: int
    date: Optional[str] = None     # ISO date string, e.g. "2025-12-03"


class SkynetPrice(BaseModel):
    tabNumber: int
    price: Optional[float] = None
    tabCurrentPrice: Optional[float] = None
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
        async with httpx.AsyncClient(timeout=30.0) as client:
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

@app.post(
    "/skynet/prices",
    response_model=List[SkynetPrice],
    dependencies=[Depends(verify_app_token)],
)
async def proxy_skynet_prices(req: SkynetPricesRequest) -> List[SkynetPrice]:
    """
    Proxy to your existing SkyNet service; hides its URL and API key
    from the app.

    Adjust the URL path and params to match your real SkyNet API.
    """
    if not SKYNET_BASE_URL:
        raise HTTPException(status_code=500, detail="SKYNET_BASE_URL not configured")

    base = SKYNET_BASE_URL.rstrip("/")
    # TODO: adjust this to your real endpoint path
    url = f"{base}/api/prices"

    headers: Dict[str, str] = {}
    if SKYNET_API_KEY:
        headers["X-API-Key"] = SKYNET_API_KEY

    params: Dict[str, Any] = {
        "meetingId": req.meeting_id,
        "raceNumber": req.race_number,
    }
    if req.date:
        params["date"] = req.date

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params, headers=headers)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"SkyNet upstream error: {exc}",
        ) from exc

    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

    data = resp.json()

    rows: List[SkynetPrice] = []

    # If your SkyNet API returns a bare list: [...]
    if isinstance(data, list):
        src = data
    else:
        # Or a wrapper: { "prices": [...] }
        src = data.get("prices", [])

    for row in src:
        if isinstance(row, dict):
            try:
                rows.append(SkynetPrice(**row))
            except TypeError:
                # If the shape doesn't match exactly, you can tweak mapping here.
                continue

    return rows


# -------------------------------------------------------------------
# Healthcheck
# -------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok"}
