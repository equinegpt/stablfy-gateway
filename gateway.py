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
from fastapi import FastAPI, HTTPException, Header, Depends, Query, Request
from fastapi.middleware.cors import CORSMiddleware
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

# Track whether the DB is reachable (referrals are non-critical)
_db_available = False


async def get_db():
    if not _db_available:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Referral database unavailable")
    async with async_session() as session:
        yield session


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _db_available
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        _db_available = True
    except Exception as e:
        print(f"[gateway] WARNING: DB connection failed ({e}). Referral endpoints disabled, all other routes OK.")
        _db_available = False
    yield
    try:
        await engine.dispose()
    except Exception:
        pass


app = FastAPI(
    title="Stablfy Gateway",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow web app origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://localhost:3000",
        "https://app.puntingform.com.au",
        "https://punting-form-web.onrender.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------------------------
# Config from environment
# -------------------------------------------------------------------

APP_TOKEN = os.getenv("APP_TOKEN", "")

IREEL_API_KEY = os.getenv("IREEL_API_KEY", "")
IREEL_BASE_URL = os.getenv("IREEL_BASE_URL", "https://api.ireel.ai/chat")

STABLFY_API_URL = os.getenv("STABLFY_API_URL", "https://api.stablfy.com")
STABLFY_USERNAME = os.getenv("STABLFY_USERNAME", "")
STABLFY_PASSWORD = os.getenv("STABLFY_PASSWORD", "")

# Cached Stablfy JWT (refreshed when expired)
_stablfy_token: Optional[str] = None
_stablfy_token_expiry: float = 0

SKYNET_BASE_URL = os.getenv("SKYNET_BASE_URL", "")
SKYNET_API_KEY = os.getenv("SKYNET_API_KEY", "")

SKYNET_PF_URL = os.getenv(
    "SKYNET_PF_URL",
    "https://puntx.puntingform.com.au/api/skynet/getskynetprices",
)

PF_API_KEY = os.getenv("PF_API_KEY", "c867b2f9-d740-4cce-b772-801708c8191d")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

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


# -------------------------------------------------------------------
# SignalR token broker — issues short-lived JWT for direct Stablfy API
# -------------------------------------------------------------------

class SignalRTokenResponse(BaseModel):
    token: str
    hub_url: str
    expires_in: int  # seconds until token expires (approximate)


# Simple rate limiter: track last token issue per app-token
_token_issue_times: Dict[str, float] = {}
_TOKEN_COOLDOWN_SECONDS = 30  # min seconds between token requests


@app.post(
    "/auth/signalr-token",
    response_model=SignalRTokenResponse,
    dependencies=[Depends(verify_app_token)],
)
async def issue_signalr_token(x_app_token: str = Header(...)) -> SignalRTokenResponse:
    """
    Token broker: app authenticates with APP_TOKEN, gateway logs into
    Stablfy API with server-side credentials, returns a short-lived JWT
    for the app to use with the SignalR hub directly.

    Security:
    - Stablfy credentials (username/password) never leave the server
    - App only receives a short-lived JWT (Stablfy controls TTL)
    - Refresh token is NOT returned — app must come back here for a new JWT
    - Rate limited to prevent abuse (one token per 30 seconds per client)
    """
    if not STABLFY_API_URL or not STABLFY_USERNAME or not STABLFY_PASSWORD:
        raise HTTPException(
            status_code=500,
            detail="Stablfy API credentials not configured on gateway",
        )

    # Rate limit: prevent rapid token requests
    now = time.time()
    last_issue = _token_issue_times.get(x_app_token, 0)
    if now - last_issue < _TOKEN_COOLDOWN_SECONDS:
        remaining = int(_TOKEN_COOLDOWN_SECONDS - (now - last_issue))
        raise HTTPException(
            status_code=429,
            detail=f"Token rate limited. Try again in {remaining}s.",
        )

    # Login to Stablfy API
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{STABLFY_API_URL}/api/common/account/login",
                json={
                    "userName": STABLFY_USERNAME,
                    "password": STABLFY_PASSWORD,
                },
                headers={
                    "Content-Type": "application/json",
                    "Origin": "https://admin.stablfy.com",
                    "Referer": "https://admin.stablfy.com/",
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        print(f"[GW AUTH] Stablfy login failed: {exc.response.status_code}")
        raise HTTPException(
            status_code=502,
            detail="Failed to authenticate with Stablfy API",
        )
    except Exception as exc:
        print(f"[GW AUTH] Stablfy login error: {exc}")
        raise HTTPException(
            status_code=502,
            detail="Stablfy API unreachable",
        )

    token = data.get("token")
    if not token:
        raise HTTPException(
            status_code=502,
            detail="No token in Stablfy login response",
        )

    # Record issue time for rate limiting
    _token_issue_times[x_app_token] = now

    # TTL from Stablfy response (seconds), default to 3600 if not provided
    ttl = data.get("ttl", 3600)

    hub_url = f"{STABLFY_API_URL}/hubs/ai"

    print(f"[GW AUTH] Issued SignalR token (TTL={ttl}s)")

    return SignalRTokenResponse(
        token=token,
        hub_url=hub_url,
        expires_in=int(ttl),
    )


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
# Gemini AI chat (via Stablfy API — replaces iReel)
# -------------------------------------------------------------------

# In-memory token cache for Gemini auth
_gemini_token: Optional[str] = None


async def _gemini_login() -> str:
    """Login to Stablfy API and return bearer token."""
    global _gemini_token
    if not STABLFY_USERNAME or not STABLFY_PASSWORD:
        raise HTTPException(status_code=500, detail="STABLFY_USERNAME/PASSWORD not configured")

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{STABLFY_API_URL}/api/common/account/login",
            json={"userName": STABLFY_USERNAME, "password": STABLFY_PASSWORD},
            headers={
                "Content-Type": "application/json",
                "Origin": "https://admin.stablfy.com",
                "Referer": "https://admin.stablfy.com/",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        _gemini_token = data["token"]
        print(f"[GW GEMINI] Logged in as {data.get('firstName', '?')}")
        return _gemini_token


async def _gemini_auth_headers(force_refresh: bool = False) -> Dict[str, str]:
    """Get auth headers, logging in if needed (or forced)."""
    global _gemini_token
    if force_refresh:
        _gemini_token = None
    if not _gemini_token:
        await _gemini_login()
    return {
        "Authorization": f"Bearer {_gemini_token}",
        "Content-Type": "application/json",
        "Origin": "https://admin.stablfy.com",
        "Referer": "https://admin.stablfy.com/",
    }


@app.post(
    "/gemini/chat",
    response_model=IreelChatResponse,
    dependencies=[Depends(verify_app_token)],
)
async def proxy_gemini_chat(req: IreelChatRequest) -> IreelChatResponse:
    """
    Gemini AI chat endpoint — replaces iReel for live app calls.

    Uses the Stablfy API (create conversation → poll for response).
    Returns the same response shape as /ireel/chat for compatibility.
    """
    if not STABLFY_API_URL or not STABLFY_USERNAME:
        raise HTTPException(status_code=500, detail="Gemini not configured")

    headers = await _gemini_auth_headers()
    base = STABLFY_API_URL.rstrip("/")

    # 1) Create conversation
    title = f"App: {req.prompt[:50]}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{base}/api/admin/ai/conversations",
                json={"kind": 0, "title": title, "initialMessage": req.prompt},
                headers=headers,
            )

            # Re-login on 401 (token expired) and retry once
            if resp.status_code == 401:
                print("[GW GEMINI] 401 on create — refreshing token and retrying")
                headers = await _gemini_auth_headers(force_refresh=True)
                resp = await client.post(
                    f"{base}/api/admin/ai/conversations",
                    json={"kind": 0, "title": title, "initialMessage": req.prompt},
                    headers=headers,
                )

            resp.raise_for_status()
            conv = resp.json()
    except httpx.HTTPStatusError as exc:
        body = (exc.response.text or "")[:200]
        print(f"[GW GEMINI] upstream {exc.response.status_code}: {body}")
        raise HTTPException(
            status_code=502,
            detail=f"Gemini upstream {exc.response.status_code}: {body}",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Gemini error: {exc}") from exc

    conv_id = conv.get("id")
    if not conv_id:
        raise HTTPException(status_code=502, detail="Failed to create Gemini conversation")

    print(f"[GW GEMINI] Created conversation {conv_id}")

    # 2) Poll for response (max 120s)
    import asyncio
    response_text = ""
    poll_start = time.time()

    try:
        while time.time() - poll_start < 120:
            await asyncio.sleep(3)

            async with httpx.AsyncClient(timeout=15.0) as client:
                poll_resp = await client.get(
                    f"{base}/api/admin/ai/conversations/{conv_id}",
                    headers=headers,
                )
                # Token expired mid-poll — refresh and retry
                if poll_resp.status_code == 401:
                    print("[GW GEMINI] 401 on poll — refreshing token")
                    headers = await _gemini_auth_headers(force_refresh=True)
                    poll_resp = await client.get(
                        f"{base}/api/admin/ai/conversations/{conv_id}",
                        headers=headers,
                    )
                if poll_resp.status_code != 200:
                    continue

                conv_data = poll_resp.json()
                messages = conv_data.get("messages", [])

                for msg in messages:
                    if msg.get("role") == 1:  # assistant
                        status = msg.get("status", 0)
                        if status == 2:  # succeeded
                            response_text = msg.get("content", "")
                            elapsed = time.time() - poll_start
                            print(f"[GW GEMINI] Response in {elapsed:.1f}s")
                            break
                        elif status == 3:  # failed
                            raise HTTPException(
                                status_code=502,
                                detail="Gemini AI failed to respond",
                            )

                if response_text:
                    break

        if not response_text:
            raise HTTPException(status_code=504, detail="Gemini timeout (120s)")

    finally:
        # 3) Cleanup conversation
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.delete(
                    f"{base}/api/admin/ai/conversations/{conv_id}",
                    headers=headers,
                )
        except Exception:
            pass

    return IreelChatResponse(
        response=response_text,
        raw={"source": "gemini", "conversation_id": conv_id},
    )


# -------------------------------------------------------------------
# Gemini proxy (for Punting Form web app)
# -------------------------------------------------------------------

class GeminiChatRequest(BaseModel):
    prompt: str
    system_context: Optional[str] = None

class GeminiChatResponse(BaseModel):
    response: str

@app.post(
    "/gemini/chat",
    response_model=GeminiChatResponse,
    dependencies=[Depends(verify_app_token)],
)
async def proxy_gemini_chat(req: GeminiChatRequest) -> GeminiChatResponse:
    """
    Proxy chat requests to Google Gemini API.
    Used by the Punting Form web app for AI analysis.
    """
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"

    # Build Gemini request
    contents = []
    if req.system_context:
        contents.append({
            "role": "user",
            "parts": [{"text": f"System instructions: {req.system_context}"}]
        })
        contents.append({
            "role": "model",
            "parts": [{"text": "Understood. I'll follow these instructions."}]
        })
    contents.append({
        "role": "user",
        "parts": [{"text": req.prompt}]
    })

    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 2048,
        }
    }

    print(f"[GW GEMINI] prompt length={len(req.prompt)}")

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(url, json=payload)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Gemini upstream error: {exc}") from exc

    if resp.status_code >= 400:
        print(f"[GW GEMINI] Error {resp.status_code}: {resp.text[:300]}")
        raise HTTPException(status_code=resp.status_code, detail=resp.text[:300] or "Gemini error")

    try:
        data = resp.json()
        # Extract text from Gemini response
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            text = " ".join(p.get("text", "") for p in parts).strip()
            print(f"[GW GEMINI] OK, response length={len(text)}")
            return GeminiChatResponse(response=text)
        raise HTTPException(status_code=502, detail="No candidates in Gemini response")
    except (ValueError, KeyError, IndexError) as exc:
        raise HTTPException(status_code=502, detail=f"Invalid Gemini response: {exc}")


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
    horse: str | None = None         # Runner name (added so TRS can synthesise tips)
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

    # Upstream is slow on big race days (Sat ~45-60s for 20+ tracks).
    # Bumped read timeout from 35s to 90s.
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(90.0, connect=10.0, read=90.0)
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
                horse_name = (
                    row.get("horse")
                    or row.get("horseName")
                    or row.get("runner")
                    or row.get("runnerName")
                    or row.get("name")
                )

                # Need at least race + TAB to be useful
                if tab_no is None or race_no is None:
                    continue

                prices.append(
                    SkynetPrice(
                        track=track_name,
                        raceNumber=int(race_no),
                        tabNumber=int(tab_no),
                        horse=horse_name,
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
    Proxy PF races for a meeting — used by HK/NZ international meetings only.
    (AU races come from RA Crawler, not this endpoint.)

    Calls PF /v2/form/meeting (the only PF endpoint that returns race data)
    and normalises the response: strips bulky runner data (~340KB → ~2KB)
    and returns payLoad as a flat race list so both iOS and Flutter parse it.
    """
    if not PF_API_KEY:
        raise HTTPException(status_code=500, detail="PF_API_KEY not configured")

    url = f"{PF_BASE_URL}/v2/form/meeting"
    params = {
        "apiKey": PF_API_KEY,
        "meetingId": meetingId,
    }

    print(f"[GW PF RACES] GET {url} meetingId={meetingId}")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, params=params)
    except httpx.RequestError as exc:
        print(f"[GW PF RACES] network error for meetingId={meetingId}: {exc}")
        return []

    if resp.status_code >= 400:
        print(f"[GW PF RACES] HTTP {resp.status_code} for meetingId={meetingId}")
        return []

    try:
        data = resp.json()
    except ValueError:
        print(f"[GW PF RACES] invalid JSON for meetingId={meetingId}")
        return []

    # PF /v2/form/meeting returns payLoad as a dict: {track, races, ...}
    payload = data.get("payLoad") if isinstance(data, dict) else None
    raw_races = []
    if isinstance(payload, dict):
        raw_races = payload.get("races") or []
    elif isinstance(payload, list):
        raw_races = payload

    if not raw_races:
        print(f"[GW PF RACES] no races in response for meetingId={meetingId}")
        return []

    # Strip runner data — apps only need race-level fields.
    slim_races = []
    for r in raw_races:
        slim_races.append({
            "raceId": r.get("raceId"),
            "number": r.get("number"),
            "raceNumber": r.get("number"),
            "name": r.get("name"),
            "distance": r.get("distance"),
            "distance_m": r.get("distance"),
            "startTime": r.get("startTime"),
            "startTimeUTC": r.get("startTimeUTC"),
            "raceClass": r.get("raceClass"),
            "prizeMoney": r.get("prizeMoney"),
        })

    print(f"[GW PF RACES] OK meetingId={meetingId} → {len(slim_races)} races")
    return {"statusCode": 200, "payLoad": slim_races}


@app.get(
    "/pf/form",
    dependencies=[Depends(verify_app_token)],
)
async def proxy_pf_form(
    meetingId: int = Query(..., description="PF meeting ID"),
    raceNumber: int = Query(0, description="Race number (0 = all races)"),
    runs: int = Query(3, description="Historical runs per horse (max 10)"),
):
    """
    Proxy PF Form API — full race card with jockey, trainer, weight, barrier, form.
    Returns raw PF JSON.
    """
    if not PF_API_KEY:
        raise HTTPException(status_code=500, detail="PF_API_KEY not configured")

    url = "https://api.puntingform.com.au/v2/form/form"
    params = {
        "meetingId": meetingId,
        "raceNumber": raceNumber,
        "runs": runs,
        "apiKey": PF_API_KEY,
    }

    print(f"[GW PF FORM] GET {url} meetingId={meetingId} raceNumber={raceNumber}")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, params=params)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"PF upstream error: {exc}") from exc

    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text[:300] or "PF error")

    body_text = (resp.text or "").strip()
    if not body_text:
        raise HTTPException(status_code=502, detail="Empty response from PF")

    try:
        data = resp.json()
    except ValueError:
        raise HTTPException(status_code=502, detail="Invalid JSON from PF")

    print(f"[GW PF FORM] OK meetingId={meetingId} raceNumber={raceNumber} runners={len(data.get('payLoad', []))}")
    return data


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
# Speed Maps proxy (Punting Form speed maps)
# -------------------------------------------------------------------

@app.get(
    "/speedmaps",
    dependencies=[Depends(verify_app_token)],
)
async def proxy_speedmaps(
    meetingId: int = Query(...),
    raceNo: int = Query(...),
):
    """
    Proxy speed map data from the PuntingForm Speedmaps endpoint.
    Returns raw PF JSON — the iOS app handles parsing.
    """
    if not PF_API_KEY:
        raise HTTPException(status_code=500, detail="PF_API_KEY not configured")

    url = "https://api.puntingform.com.au/v2/User/Speedmaps"
    params = {
        "meetingId": meetingId,
        "raceNo": raceNo,
        "apiKey": PF_API_KEY,
    }

    print(f"[GW SPEEDMAPS] GET {url} meetingId={meetingId} raceNo={raceNo}")

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

    print(f"[GW SPEEDMAPS] OK meetingId={meetingId} raceNo={raceNo}")
    return data


# -------------------------------------------------------------------
# Racing DB proxy (horse search + profile)
# -------------------------------------------------------------------

RACING_DB_API_URL = os.getenv("RACING_DB_API_URL", "").rstrip("/")


@app.get(
    "/racing/horse/search",
    dependencies=[Depends(verify_app_token)],
)
async def proxy_horse_search(
    q: str = Query(..., min_length=2),
    limit: int = Query(5, le=20),
):
    """Proxy horse name search to racing-db API."""
    if not RACING_DB_API_URL:
        raise HTTPException(status_code=500, detail="RACING_DB_API_URL not configured")

    url = f"{RACING_DB_API_URL}/api/v1/horse/search"
    params = {"q": q, "limit": limit}

    print(f"[GW RACING] GET {url} q={q}")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params=params)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Racing DB error: {exc}") from exc

    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text[:300])

    return resp.json()


@app.get(
    "/racing/horse/{horse_code}",
    dependencies=[Depends(verify_app_token)],
)
async def proxy_horse_profile(
    horse_code: str,
    form_limit: int = Query(10, le=50),
):
    """Proxy horse profile to racing-db API."""
    if not RACING_DB_API_URL:
        raise HTTPException(status_code=500, detail="RACING_DB_API_URL not configured")

    url = f"{RACING_DB_API_URL}/api/v1/horse/{horse_code}"
    params = {"form_limit": form_limit}

    print(f"[GW RACING] GET {url}")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params=params)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Racing DB error: {exc}") from exc

    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text[:300])

    return resp.json()


# -------------------------------------------------------------------
# TRS proxy (Tips Results Service — for web app CORS)
# -------------------------------------------------------------------

TRS_BASE_URL = os.getenv("TRS_BASE_URL", "https://tips-results-service.onrender.com")

@app.get(
    "/trs/tips",
    dependencies=[Depends(verify_app_token)],
)
async def proxy_trs_tips(date: str = Query(...)):
    """Proxy TRS tips endpoint — adds CORS for web app."""
    url = f"{TRS_BASE_URL}/tips"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, params={"date": date})
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text[:300])
        return resp.json()
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"TRS error: {exc}") from exc


# -------------------------------------------------------------------
# CAS proxy (Canned Answers Service — for web app CORS)
# -------------------------------------------------------------------

CAS_BASE_URL = os.getenv("CAS_BASE_URL", "https://canned-answers-service.onrender.com")

@app.api_route(
    "/cas/{path:path}",
    methods=["GET", "POST"],
    dependencies=[Depends(verify_app_token)],
)
async def proxy_cas(path: str, request: Request):
    """Proxy all CAS requests — adds CORS for web app."""
    url = f"{CAS_BASE_URL}/{path}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if request.method == "POST":
                body = await request.body()
                resp = await client.post(url, content=body, headers={"Content-Type": "application/json"})
            else:
                resp = await client.get(url, params=dict(request.query_params))
        # Pass through the response as-is (let client handle 404 cache misses)
        from starlette.responses import Response
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type="application/json",
        )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"CAS error: {exc}") from exc


# -------------------------------------------------------------------
# Stablfy AI chat proxy (server-side auth — no client login needed)
# -------------------------------------------------------------------

async def _get_stablfy_token() -> str:
    """Get a valid Stablfy JWT, logging in if needed."""
    global _stablfy_token, _stablfy_token_expiry

    if _stablfy_token and time.time() < _stablfy_token_expiry:
        return _stablfy_token

    if not STABLFY_USERNAME or not STABLFY_PASSWORD:
        raise HTTPException(status_code=500, detail="STABLFY credentials not configured")

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{STABLFY_API_URL}/api/common/account/login",
            json={"userName": STABLFY_USERNAME, "password": STABLFY_PASSWORD},
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Stablfy login failed: {resp.status_code}")

    data = resp.json()
    _stablfy_token = data.get("token")
    ttl = data.get("ttl", 1200)  # default 20 min
    _stablfy_token_expiry = time.time() + (ttl * 0.8)  # refresh at 80%

    print(f"[GW STABLFY] Logged in, token valid for {ttl}s")
    return _stablfy_token


class StablfyChatRequest(BaseModel):
    prompt: str


class StablfyChatResponse(BaseModel):
    response: str


@app.post(
    "/stablfy/chat",
    response_model=StablfyChatResponse,
    dependencies=[Depends(verify_app_token)],
)
async def proxy_stablfy_chat(req: StablfyChatRequest) -> StablfyChatResponse:
    """
    Send a prompt to Stablfy AI — handles auth, conversation lifecycle, polling.
    No client-side login needed. Gateway authenticates with its own credentials.
    """
    token = await _get_stablfy_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    print(f"[GW STABLFY CHAT] prompt length={len(req.prompt)}")

    async with httpx.AsyncClient(timeout=120.0) as client:
        # 1. Create conversation with initial message
        create_resp = await client.post(
            f"{STABLFY_API_URL}/api/admin/ai/conversations",
            headers=headers,
            json={"kind": 0, "initialMessage": req.prompt},
        )

        if create_resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Create conversation failed: {create_resp.status_code}")

        conv = create_resp.json()
        conv_id = conv.get("id")
        if not conv_id:
            raise HTTPException(status_code=502, detail="No conversation ID returned")

        print(f"[GW STABLFY CHAT] Created conv {conv_id}")

        # 2. Poll until assistant responds
        import asyncio
        for _ in range(60):  # max 120 seconds (60 * 2s)
            await asyncio.sleep(2)

            poll_resp = await client.get(
                f"{STABLFY_API_URL}/api/admin/ai/conversations/{conv_id}",
                headers=headers,
            )

            if poll_resp.status_code != 200:
                continue

            poll_data = poll_resp.json()
            messages = poll_data.get("messages", [])

            # Find last assistant message
            for msg in reversed(messages):
                if msg.get("role") == 1:  # assistant
                    status = msg.get("status", 0)
                    if status == 2:  # succeeded
                        content = msg.get("content", "")
                        print(f"[GW STABLFY CHAT] OK conv {conv_id}, response length={len(content)}")

                        # 3. Cleanup — delete conversation
                        try:
                            await client.delete(
                                f"{STABLFY_API_URL}/api/admin/ai/conversations/{conv_id}",
                                headers=headers,
                            )
                        except Exception:
                            pass

                        return StablfyChatResponse(response=content)

                    if status == 3:  # failed
                        content = msg.get("content", "Processing failed")
                        raise HTTPException(status_code=502, detail=content)
                    break  # found assistant msg but still processing

        # Timeout
        raise HTTPException(status_code=504, detail="AI response timed out")


# -------------------------------------------------------------------
# No Mugs Punting (v1) — aggregator routes for the NO MUGS iOS app
# Lifted from the standalone no-mugs-gateway repo; see nm_v1/__init__.py.
# -------------------------------------------------------------------

from nm_v1 import build_router as _build_nm_router

app.include_router(
    _build_nm_router(),
    dependencies=[Depends(verify_app_token)],
)


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


@app.delete("/referral/clear-redemption")
async def clear_referral_redemption(
    secret: str = Query(...),
    device_prefix: str = Query(..., description="First 8+ chars of device ID"),
    db: AsyncSession = Depends(get_db),
):
    """Admin: clear a referral redemption so the device can redeem again."""
    if secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    result = await db.execute(
        select(ReferralRedemption).where(
            ReferralRedemption.redeemer_device_id.startswith(device_prefix)
        )
    )
    redemption = result.scalar_one_or_none()
    if not redemption:
        return {"cleared": False, "message": f"No redemption found for device prefix '{device_prefix}'"}

    device_id = redemption.redeemer_device_id
    await db.delete(redemption)
    await db.commit()
    return {"cleared": True, "device_id": device_id[:8] + "..."}


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
