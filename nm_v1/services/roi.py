"""Tab 6 — ROI rollups.

Currently the only JSON-available rollup source is TRS (`/stats/range`), which
gives us AI_BEST / DANGER / VALUE per-tip-type aggregates. BoD, AI Agreement
and Clone Rank rollups don't exist as JSON anywhere yet — we surface them as
honest `pending` placeholders so the UI shows the gap rather than faking it.
"""
from __future__ import annotations

from typing import Any

from nm_v1.models import SystemROI, SystemROIPlaceholder, SystemsROIResponse

# tip_type → user-facing label. Matches the existing Stablfy AI app.
_LABELS = {
    "AI_BEST": "AI Best",
    "DANGER":  "AI Danger",
    "VALUE":   "AI Value",
}
_ORDER = ["AI_BEST", "DANGER", "VALUE"]

_PENDING: list[SystemROIPlaceholder] = [
    SystemROIPlaceholder(
        key="mugs",
        label="Mugs (BoD)",
        note="Needs a JSON rollup wrapper on /best-of-day. Coming soon.",
    ),
    SystemROIPlaceholder(
        key="agreement",
        label="AI Agreement",
        note="Needs a 3-voice convergence rollup endpoint. Coming soon.",
    ),
    SystemROIPlaceholder(
        key="clone_rank",
        label="Clone Rank",
        note="Needs a clone-only rollup endpoint. Coming soon.",
    ),
]


def _pct(fraction: Any) -> float:
    """TRS returns fractions (0.2488 = 24.88%). Convert to a normal percent."""
    if not isinstance(fraction, (int, float)):
        return 0.0
    return round(float(fraction) * 100.0, 2)


def _confidence(n: int) -> str:
    if n < 30:
        return "anecdote"
    if n < 100:
        return "moderate"
    return "ok"


def _entry_to_system(entry: dict[str, Any]) -> SystemROI | None:
    tip_type = entry.get("tip_type")
    if tip_type not in _LABELS:
        return None
    tips = int(entry.get("tips") or 0)
    return SystemROI(
        key=tip_type.lower(),
        label=_LABELS[tip_type],
        tips=tips,
        wins=int(entry.get("wins") or 0),
        places=int(entry.get("places") or 0),
        strike_pct=_pct(entry.get("win_strike_rate")),
        place_pct=_pct(entry.get("place_strike_rate")),
        roi_pct=_pct(entry.get("roi")),
        profit=round(float(entry.get("net_profit") or 0.0), 2),
        stake_per_tip=float(entry.get("stake_per_tip") or 10.0),
        sample=tips,
        confidence=_confidence(tips),
    )


def build_systems(trs_payload: dict[str, Any]) -> SystemsROIResponse:
    raw_stats = trs_payload.get("stats") or []
    systems = [s for s in (_entry_to_system(e) for e in raw_stats) if s is not None]
    systems.sort(key=lambda s: _ORDER.index(s.key.upper()) if s.key.upper() in _ORDER else 99)

    return SystemsROIResponse(
        date_from=trs_payload.get("date_from") or "",
        date_to=trs_payload.get("date_to") or "",
        stake_per_tip=float(trs_payload.get("stake_per_tip") or 10.0),
        systems=systems,
        pending=_PENDING,
    )
