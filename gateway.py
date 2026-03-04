from __future__ import annotations

import os
import secrets
import string
import time
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any, List
import datetime as dt
from datetime import date as _date, datetime

import httpx
from fastapi import FastAPI, HTTPException, Header, Depends, Query
from pydantic import BaseModel
from sqlalchemy import Column, String, DateTime, ForeignKey, select, func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase


# -------------------------------------------------------------------
# Database Setup
# -------------------------------------------------------------------

# Get DATABASE_URL and convert for async SQLAlchemy
_raw_db_url = os.getenv("DATABASE_URL", "")
if _raw_db_url:
    # Render uses postgres:// but SQLAlchemy async needs postgresql+asyncpg://
    if _raw_db_url.startswith("postgres://"):
        DATABASE_URL = _raw_db_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif _raw_db_url.startswith("postgresql://"):
        DATABASE_URL = _raw_db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    else:
        DATABASE_URL = _raw_db_url
else:
    # Fallback to SQLite for local development
    DATABASE_URL = "sqlite+aiosqlite:///./referrals.db"


class Base(DeclarativeBase):
    pass


class ReferralCode(Base):
    __tablename__ = "referral_codes"

    device_id = Column(String, primary_key=True)
    code = Column(String, unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ReferralRedemption(Base):
    __tablename__ = "referral_redemptions"

    redeemer_device_id = Column(String, primary_key=True)
    code_used = Column(String, ForeignKey("referral_codes.code"), nullable=False)
    referrer_device_id = Column(String, nullable=False)
    redeemed_at = Column(DateTime, default=datetime.utcnow)


engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with async_session() as session:
        yield session


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title="Stablfy Gateway",
    version="0.1.0",
    lifespan=lifespan,
)

# -------------------------------------------------------------------
# Config from environment
# -------------------------------------------------------------------

APP_TOKEN = os.getenv("APP_TOKEN", "")

IREEL_API_KEY = os.getenv("IREEL_API_KEY", "")
IREEL_BASE_URL = os.getenv("IREEL_BASE_URL", "https://api.ireel.ai/chat")

SKYNET_BASE_URL = os.getenv("SKYNET_BASE_URL", "")
SKYNET_API_KEY = os.getenv("SKYNET_API_KEY", "")

SKYNET_PF_URL = os.getenv(
    "SKYNET_PF_URL",
    "https://puntx.puntingform.com.au/api/skynet/getskynetprices",
)

PF_API_KEY = os.getenv("PF_API_KEY", "c867b2f9-d740-4cce-b772-801708c8191d")

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


# Referral Models
class ReferralGenerateRequest(BaseModel):
    deviceId: str


class ReferralGenerateResponse(BaseModel):
    code: str
    referralCount: int


class ReferralRedeemRequest(BaseModel):
    code: str
    deviceId: str


class ReferralRedeemResponse(BaseModel):
    success: bool
    questionsAwarded: int
    message: Optional[str] = None


class ReferralStatusResponse(BaseModel):
    hasRedeemed: bool


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

# In-memory cache: { "YYYY-MM-DD": (timestamp, [SkynetPrice, ...]) }
_skynet_cache: dict[str, tuple[float, list]] = {}
_SKYNET_CACHE_TTL = 300  # 5 minutes

class SkynetPricesRequest(BaseModel):
    # from the app: { "date": "2025-12-05" }
    date: str


class SkynetPrice(BaseModel):
    # Which race this row belongs to
    track: str | None = None         # e.g. "Cranbourne"
    raceNumber: int                  # e.g. 2

    # Runner-level info
    tabNumber: int                   # TAB no
    price: float | None = None       # AI fair price
    tabCurrentPrice: float | None = None  # TAB price
    rank: int | None = None          # model rank (if PF sends it)


@app.post(
    "/skynet/prices",
    response_model=list[SkynetPrice],
    dependencies=[Depends(verify_app_token)],
)
async def proxy_skynet_prices(req: SkynetPricesRequest):
    """
    Fetch Skynet prices for a given day from PuntingForm and return a
    trimmed structure used by the app.

    Body from app: { "date": "YYYY-MM-DD" }.

    On PF timeouts / request errors we now degrade gracefully and
    return an empty list instead of 502 so the app keeps working.
    """
    # --- In-memory cache: serve instantly if fresh ---
    cached = _skynet_cache.get(req.date)
    if cached:
        ts, rows = cached
        if time.time() - ts < _SKYNET_CACHE_TTL:
            print(f"[GW SKYNET] CACHE HIT date={req.date}, rows={len(rows)}")
            return rows

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

    # PF wants dd-MMM-yyyy; try 06-dec-2025 then 06-Dec-2025
    lower = d.strftime("%d-%b-%Y").lower()
    normal = d.strftime("%d-%b-%Y")
    date_variants = [lower, normal]

    last_exc: Exception | None = None

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(35.0, connect=10.0, read=35.0)
    ) as client:
        for meeting_date in date_variants:
            params = {
                "meetingDate": meeting_date,
                "apikey": SKYNET_API_KEY or "",
            }
            print(f"[GW SKYNET] GET {SKYNET_BASE_URL} params={params}")

            try:
                resp = await client.get(SKYNET_BASE_URL, params=params)
                # raise for 4xx/5xx so we can handle in one place
                resp.raise_for_status()
            except httpx.ReadTimeout as exc:
                # PF is just taking too long – log + try next variant
                print(
                    f"[GW SKYNET] ReadTimeout date={meeting_date} "
                    f"exc={exc!r}"
                )
                last_exc = exc
                continue
            except httpx.RequestError as exc:
                print(
                    f"[GW SKYNET] RequestError date={meeting_date} "
                    f"exc={exc!r}"
                )
                last_exc = exc
                continue
            except httpx.HTTPStatusError as exc:
                # Non-200 from PF – log; we’ll degrade gracefully below
                print(
                    f"[GW SKYNET] HTTP {resp.status_code} "
                    f"for date={meeting_date} body={resp.text[:300]!r}"
                )
                last_exc = exc
                continue

            # --- JSON shape normalisation: list or {rows:[...]} / {prices:[...]} ---
            data = resp.json()
            if isinstance(data, list):
                raw_rows = data
            elif isinstance(data, dict):
                raw_rows = data.get("rows") or data.get("prices") or []
            else:
                print(f"[GW SKYNET] Unexpected JSON type: {type(data)}")
                raw_rows = []

            prices: list[SkynetPrice] = []
            for row in raw_rows:
                if not isinstance(row, dict):
                    continue

                tab_no = row.get("tabNo") or row.get("tabNumber")
                race_no = row.get("raceNo") or row.get("raceNumber")
                track_name = row.get("venue") or row.get("track")

                # Need at least race + TAB to be useful
                if tab_no is None or race_no is None:
                    continue

                prices.append(
                    SkynetPrice(
                        track=track_name,
                        raceNumber=int(race_no),
                        tabNumber=int(tab_no),
                        price=row.get("aiPrice") or row.get("price"),
                        tabCurrentPrice=row.get("tabPrice") or row.get("tabCurrentPrice"),
                        rank=row.get("rank"),
                    )
                )

            print(f"[GW SKYNET] OK date={meeting_date}, rows={len(prices)}")
            if prices:
                _skynet_cache[req.date] = (time.time(), prices)
            return prices

    # If we get here, both variants failed.
    # Instead of 502, degrade gracefully so the app can still show tips.
    print(
        f"[GW SKYNET] giving up for {req.date}, "
        f"returning empty Skynet list; last_exc={last_exc!r}"
    )
    return []

# -------------------------------------------------------------------
# Punting Form Proxy (meetings, races, sectionals) - iOS Gateway
# -------------------------------------------------------------------

PF_BASE_URL = "https://api.puntingform.com.au"


@app.get(
    "/pf/meetings",
    dependencies=[Depends(verify_app_token)],
)
async def proxy_pf_meetings(
    meetingDate: str = Query(..., description="Date in 'd MMM yyyy' format e.g. '22 Oct 2025'"),
):
    """
    Proxy PF meetings list - iOS app calls this instead of PF directly.
    No API key in the app; we add it server-side.
    """
    if not PF_API_KEY:
        raise HTTPException(status_code=500, detail="PF_API_KEY not configured")

    url = f"{PF_BASE_URL}/v2/form/meetingslist"
    params = {
        "apiKey": PF_API_KEY,
        "meetingDate": meetingDate,
        "includeRaces": "true",
    }

    print(f"[GW PF MEETINGS] GET {url} meetingDate={meetingDate}")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, params=params)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"PF upstream error: {exc}",
        ) from exc

    if resp.status_code >= 400:
        raise HTTPException(
            status_code=resp.status_code,
            detail=resp.text[:300] or "PF error",
        )

    body_text = (resp.text or "").strip()
    if not body_text:
        raise HTTPException(status_code=502, detail="Empty response from PF")

    try:
        data = resp.json()
    except ValueError:
        raise HTTPException(status_code=502, detail="Invalid JSON from PF")

    print(f"[GW PF MEETINGS] OK meetingDate={meetingDate}")
    return data


@app.get(
    "/pf/races",
    dependencies=[Depends(verify_app_token)],
)
async def proxy_pf_races(
    meetingId: str = Query(..., description="PF meeting ID"),
):
    """
    Proxy PF races list for a meeting - iOS app calls this instead of PF directly.
    Tries multiple endpoint variants since PF API can be inconsistent.
    """
    if not PF_API_KEY:
        raise HTTPException(status_code=500, detail="PF_API_KEY not configured")

    # Candidate PF endpoints (same as iOS client tries)
    endpoints = [
        f"{PF_BASE_URL}/v2/form/raceslist",
        f"{PF_BASE_URL}/v2/form/races",
        f"{PF_BASE_URL}/v2/form/meetingraces",
        f"{PF_BASE_URL}/v2/form/meeting/races",
        f"{PF_BASE_URL}/v2/form/races/list",
        f"{PF_BASE_URL}/v2/form/raceday",
        f"{PF_BASE_URL}/v2/form/racecard",
        f"{PF_BASE_URL}/v2/form/meeting",
    ]

    params = {
        "apiKey": PF_API_KEY,
        "meetingId": meetingId,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        for url in endpoints:
            print(f"[GW PF RACES] trying {url} meetingId={meetingId}")
            try:
                resp = await client.get(url, params=params)
                if resp.status_code < 400:
                    body_text = (resp.text or "").strip()
                    if body_text:
                        data = resp.json()
                        print(f"[GW PF RACES] OK from {url}")
                        return data
            except (httpx.RequestError, ValueError):
                continue

    # None worked - return empty
    print(f"[GW PF RACES] all endpoints failed for meetingId={meetingId}")
    return []


@app.get(
    "/pf/sectionals",
    dependencies=[Depends(verify_app_token)],
)
async def proxy_pf_sectionals(
    meetingId: str = Query(..., description="PF meeting ID"),
    raceNumber: int = Query(..., description="Race number"),
):
    """
    Proxy PF sectionals/iReel race data - iOS app calls this instead of PF directly.
    Returns raw PF JSON — the iOS app handles parsing.
    """
    if not PF_API_KEY:
        raise HTTPException(status_code=500, detail="PF_API_KEY not configured")

    url = f"{PF_BASE_URL}/v2/ireel/race"
    params = {
        "meetingId": meetingId,
        "raceNumber": raceNumber,
        "apiKey": PF_API_KEY,
    }

    print(f"[GW PF SECTIONALS] GET {url} meetingId={meetingId} raceNumber={raceNumber}")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, params=params)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"PF upstream error: {exc}",
        ) from exc

    if resp.status_code >= 400:
        raise HTTPException(
            status_code=resp.status_code,
            detail=resp.text[:300] or "PF error",
        )

    body_text = (resp.text or "").strip()
    if not body_text:
        raise HTTPException(status_code=502, detail="Empty response from PF")

    try:
        data = resp.json()
    except ValueError:
        raise HTTPException(status_code=502, detail="Invalid JSON from PF")

    print(f"[GW PF SECTIONALS] OK meetingId={meetingId} raceNumber={raceNumber}")
    return data


# -------------------------------------------------------------------
# Sectionals proxy (Legacy - keeping for backwards compat)
# -------------------------------------------------------------------

@app.get(
    "/sectionals",
    dependencies=[Depends(verify_app_token)],
)
async def proxy_sectionals(
    meetingId: int = Query(...),
    raceNumber: int = Query(...),
):
    """
    Proxy sectional times from the PuntingForm iReel race endpoint.
    Returns raw PF JSON — the Flutter app handles parsing.
    """
    if not PF_API_KEY:
        raise HTTPException(status_code=500, detail="PF_API_KEY not configured")

    url = "https://api.puntingform.com.au/v2/ireel/race"
    params = {
        "meetingId": meetingId,
        "raceNumber": raceNumber,
        "apiKey": PF_API_KEY,
    }

    print(f"[GW SECTIONALS] GET {url} meetingId={meetingId} raceNumber={raceNumber}")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, params=params)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"PF upstream error: {exc}",
        ) from exc

    if resp.status_code >= 400:
        raise HTTPException(
            status_code=resp.status_code,
            detail=resp.text[:300] or "PF error",
        )

    body_text = (resp.text or "").strip()
    if not body_text:
        raise HTTPException(status_code=502, detail="Empty response from PF")

    try:
        data = resp.json()
    except ValueError:
        raise HTTPException(status_code=502, detail="Invalid JSON from PF")

    print(f"[GW SECTIONALS] OK meetingId={meetingId} raceNumber={raceNumber}")
    return data


# -------------------------------------------------------------------
# Healthcheck
# -------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/debug/config")
async def debug_config():
    """Debug endpoint to check configuration (remove in production)."""
    return {
        "pf_api_key_set": bool(PF_API_KEY),
        "pf_api_key_length": len(PF_API_KEY) if PF_API_KEY else 0,
        "pf_api_key_preview": f"{PF_API_KEY[:8]}...{PF_API_KEY[-4:]}" if PF_API_KEY and len(PF_API_KEY) > 12 else "too_short",
        "pf_base_url": PF_BASE_URL,
    }


# -------------------------------------------------------------------
# Referral Endpoints
# -------------------------------------------------------------------

def generate_referral_code() -> str:
    chars = string.ascii_uppercase + string.digits
    random_part = "".join(secrets.choice(chars) for _ in range(6))
    return f"STAB-{random_part}"


@app.post(
    "/referral/generate",
    response_model=ReferralGenerateResponse,
    dependencies=[Depends(verify_app_token)],
)
async def referral_generate(
    req: ReferralGenerateRequest, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(ReferralCode).where(ReferralCode.device_id == req.deviceId)
    )
    existing = result.scalar_one_or_none()

    if existing:
        count_result = await db.execute(
            select(func.count())
            .select_from(ReferralRedemption)
            .where(ReferralRedemption.code_used == existing.code)
        )
        referral_count = count_result.scalar() or 0
        return ReferralGenerateResponse(code=existing.code, referralCount=referral_count)

    for _ in range(10):
        new_code = generate_referral_code()
        check = await db.execute(
            select(ReferralCode).where(ReferralCode.code == new_code)
        )
        if not check.scalar_one_or_none():
            break
    else:
        raise HTTPException(status_code=500, detail="Failed to generate unique code")

    referral_code = ReferralCode(device_id=req.deviceId, code=new_code)
    db.add(referral_code)
    await db.commit()

    return ReferralGenerateResponse(code=new_code, referralCount=0)


@app.post(
    "/referral/redeem",
    response_model=ReferralRedeemResponse,
    dependencies=[Depends(verify_app_token)],
)
async def referral_redeem(
    req: ReferralRedeemRequest, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(ReferralCode).where(ReferralCode.code == req.code.upper())
    )
    referral_code = result.scalar_one_or_none()

    if not referral_code:
        return ReferralRedeemResponse(
            success=False, questionsAwarded=0, message="Invalid referral code"
        )

    if referral_code.device_id == req.deviceId:
        return ReferralRedeemResponse(
            success=False,
            questionsAwarded=0,
            message="You can't use your own referral code",
        )

    existing_redemption = await db.execute(
        select(ReferralRedemption).where(
            ReferralRedemption.redeemer_device_id == req.deviceId
        )
    )
    if existing_redemption.scalar_one_or_none():
        return ReferralRedeemResponse(
            success=False,
            questionsAwarded=0,
            message="You have already used a referral code",
        )

    redemption = ReferralRedemption(
        redeemer_device_id=req.deviceId,
        code_used=req.code.upper(),
        referrer_device_id=referral_code.device_id,
    )
    db.add(redemption)
    await db.commit()

    return ReferralRedeemResponse(success=True, questionsAwarded=50, message=None)


@app.get(
    "/referral/status",
    response_model=ReferralStatusResponse,
    dependencies=[Depends(verify_app_token)],
)
async def referral_status(
    deviceId: str = Query(...), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(ReferralRedemption).where(
            ReferralRedemption.redeemer_device_id == deviceId
        )
    )
    has_redeemed = result.scalar_one_or_none() is not None
    return ReferralStatusResponse(hasRedeemed=has_redeemed)


# -------------------------------------------------------------------
# Referral Admin Dashboard & Stats
# -------------------------------------------------------------------

ADMIN_SECRET = os.getenv("ADMIN_SECRET", "stablfy-admin-2026")


class ReferralStatsResponse(BaseModel):
    total_codes: int
    total_redemptions: int
    questions_awarded: int
    top_referrers: list
    recent_redemptions: list


@app.get("/referral/stats")
async def referral_stats(
    secret: str = Query(..., description="Admin secret for access"),
    db: AsyncSession = Depends(get_db),
):
    """
    JSON stats endpoint for referral program.
    Access: /referral/stats?secret=<ADMIN_SECRET>
    """
    if secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    # Total codes generated
    codes_result = await db.execute(select(func.count()).select_from(ReferralCode))
    total_codes = codes_result.scalar() or 0

    # Total redemptions
    redemptions_result = await db.execute(
        select(func.count()).select_from(ReferralRedemption)
    )
    total_redemptions = redemptions_result.scalar() or 0

    # Questions awarded (50 per redemption)
    questions_awarded = total_redemptions * 50

    # Top referrers (by redemption count)
    top_referrers_result = await db.execute(
        select(
            ReferralCode.code,
            ReferralCode.device_id,
            func.count(ReferralRedemption.redeemer_device_id).label("count"),
        )
        .outerjoin(ReferralRedemption, ReferralCode.code == ReferralRedemption.code_used)
        .group_by(ReferralCode.code, ReferralCode.device_id)
        .order_by(func.count(ReferralRedemption.redeemer_device_id).desc())
        .limit(10)
    )
    top_referrers = [
        {
            "code": row.code,
            "device_id": row.device_id[:8] + "...",  # Truncate for privacy
            "redemptions": row.count,
            "questions_earned": row.count * 50,
        }
        for row in top_referrers_result.all()
    ]

    # Recent redemptions (last 20)
    recent_result = await db.execute(
        select(ReferralRedemption)
        .order_by(ReferralRedemption.redeemed_at.desc())
        .limit(20)
    )
    recent_redemptions = [
        {
            "code": r.code_used,
            "redeemer": r.redeemer_device_id[:8] + "...",
            "referrer": r.referrer_device_id[:8] + "...",
            "redeemed_at": r.redeemed_at.isoformat() if r.redeemed_at else None,
        }
        for r in recent_result.scalars().all()
    ]

    return ReferralStatsResponse(
        total_codes=total_codes,
        total_redemptions=total_redemptions,
        questions_awarded=questions_awarded,
        top_referrers=top_referrers,
        recent_redemptions=recent_redemptions,
    )


from fastapi.responses import HTMLResponse


@app.get("/referral/dashboard", response_class=HTMLResponse)
async def referral_dashboard(
    secret: str = Query(..., description="Admin secret for access"),
    db: AsyncSession = Depends(get_db),
):
    """
    Simple HTML dashboard for referral program stats.
    Access: /referral/dashboard?secret=<ADMIN_SECRET>
    """
    if secret != ADMIN_SECRET:
        return HTMLResponse(
            content="<h1>403 Forbidden</h1><p>Invalid admin secret</p>",
            status_code=403,
        )

    # Fetch stats
    codes_result = await db.execute(select(func.count()).select_from(ReferralCode))
    total_codes = codes_result.scalar() or 0

    redemptions_result = await db.execute(
        select(func.count()).select_from(ReferralRedemption)
    )
    total_redemptions = redemptions_result.scalar() or 0
    questions_awarded = total_redemptions * 50

    # Top referrers
    top_referrers_result = await db.execute(
        select(
            ReferralCode.code,
            ReferralCode.device_id,
            ReferralCode.created_at,
            func.count(ReferralRedemption.redeemer_device_id).label("count"),
        )
        .outerjoin(ReferralRedemption, ReferralCode.code == ReferralRedemption.code_used)
        .group_by(ReferralCode.code, ReferralCode.device_id, ReferralCode.created_at)
        .order_by(func.count(ReferralRedemption.redeemer_device_id).desc())
        .limit(15)
    )
    top_referrers = top_referrers_result.all()

    # Recent redemptions
    recent_result = await db.execute(
        select(ReferralRedemption)
        .order_by(ReferralRedemption.redeemed_at.desc())
        .limit(20)
    )
    recent_redemptions = recent_result.scalars().all()

    # Build HTML
    referrers_rows = ""
    for r in top_referrers:
        created = r.created_at.strftime("%d %b %Y") if r.created_at else "—"
        referrers_rows += f"""
        <tr>
            <td><code>{r.code}</code></td>
            <td>{r.device_id[:12]}...</td>
            <td>{created}</td>
            <td><strong>{r.count}</strong></td>
            <td>{r.count * 50}</td>
        </tr>
        """

    redemptions_rows = ""
    for r in recent_redemptions:
        redeemed = r.redeemed_at.strftime("%d %b %Y %H:%M") if r.redeemed_at else "—"
        redemptions_rows += f"""
        <tr>
            <td><code>{r.code_used}</code></td>
            <td>{r.redeemer_device_id[:12]}...</td>
            <td>{r.referrer_device_id[:12]}...</td>
            <td>{redeemed}</td>
        </tr>
        """

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Stablfy Referral Dashboard</title>
        <style>
            * {{ box-sizing: border-box; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: #1a1a2e;
                color: #eee;
                margin: 0;
                padding: 20px;
            }}
            h1 {{ color: #FFD700; margin-bottom: 5px; }}
            .subtitle {{ color: #888; margin-bottom: 30px; }}
            .stats {{
                display: flex;
                gap: 20px;
                flex-wrap: wrap;
                margin-bottom: 30px;
            }}
            .stat-card {{
                background: #2a2a4a;
                border-radius: 12px;
                padding: 20px 30px;
                min-width: 180px;
            }}
            .stat-card h3 {{ margin: 0; color: #888; font-size: 14px; }}
            .stat-card .value {{ font-size: 36px; font-weight: bold; color: #FFD700; }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-bottom: 30px;
                background: #2a2a4a;
                border-radius: 12px;
                overflow: hidden;
            }}
            th, td {{
                padding: 12px 16px;
                text-align: left;
                border-bottom: 1px solid #3a3a5a;
            }}
            th {{ background: #3a3a5a; color: #FFD700; }}
            tr:hover {{ background: #3a3a5a; }}
            code {{
                background: #3a3a5a;
                padding: 2px 8px;
                border-radius: 4px;
                font-size: 13px;
            }}
            .section-title {{ color: #FFD700; margin: 30px 0 15px 0; }}
            .refresh {{ color: #888; font-size: 12px; }}
        </style>
    </head>
    <body>
        <h1>Stablfy Referral Dashboard</h1>
        <p class="subtitle">Friends Referral Program Stats</p>

        <div class="stats">
            <div class="stat-card">
                <h3>Total Codes</h3>
                <div class="value">{total_codes}</div>
            </div>
            <div class="stat-card">
                <h3>Redemptions</h3>
                <div class="value">{total_redemptions}</div>
            </div>
            <div class="stat-card">
                <h3>Questions Awarded</h3>
                <div class="value">{questions_awarded}</div>
            </div>
            <div class="stat-card">
                <h3>Conversion</h3>
                <div class="value">{(total_redemptions / total_codes * 100) if total_codes > 0 else 0:.1f}%</div>
            </div>
        </div>

        <h2 class="section-title">Top Referrers</h2>
        <table>
            <thead>
                <tr>
                    <th>Code</th>
                    <th>Device ID</th>
                    <th>Created</th>
                    <th>Redemptions</th>
                    <th>Questions Earned</th>
                </tr>
            </thead>
            <tbody>
                {referrers_rows if referrers_rows else '<tr><td colspan="5" style="text-align:center;color:#888;">No referral codes yet</td></tr>'}
            </tbody>
        </table>

        <h2 class="section-title">Recent Redemptions</h2>
        <table>
            <thead>
                <tr>
                    <th>Code Used</th>
                    <th>Redeemer</th>
                    <th>Referrer</th>
                    <th>Redeemed At</th>
                </tr>
            </thead>
            <tbody>
                {redemptions_rows if redemptions_rows else '<tr><td colspan="4" style="text-align:center;color:#888;">No redemptions yet</td></tr>'}
            </tbody>
        </table>

        <p class="refresh">Refresh page to update stats</p>
    </body>
    </html>
    """

    return HTMLResponse(content=html)
