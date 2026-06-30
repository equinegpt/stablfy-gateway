"""Tab 1 (Mugs) — BoD + four production lanes (L4 / L2 / L1 / L3).

Lifts /api/curated from stablfy-social and reshapes it for the iOS Mugs tab:

  * best_of_day: the 3 daily picks (cap from BOD_MAX_PICKS upstream). Each
    carries its source_lane and is_star_tier flag.
  * lanes: the four production lanes, with hard-coded 9-week audit stats
    (Apr 23 → Jun 26) so the user sees real backtest ROI alongside today's
    picks.

Research-only lanes (V_value, P_divergence, S_steam) are deliberately
dropped — they don't validate on the executable feed per the
stablfy-social handoff doc (2026-06-29).

★ tier: a pick is starred when it's in L4_class AND `gemini_position`
on the play == "AI_BEST". That intersection ran +34.7% ROI on n=222
in the audit — the only meaningful standout in the lane system.
"""
from __future__ import annotations

from typing import Any

from nm_v1.models import Lane, LaneAudit, MugPick, MugsResponse
from nm_v1.services.race_times import build_race_time_index, race_time_for


# Production lane definitions. Order = display order. Audit stats from
# stablfy-social audit Apr 23 → Jun 26 (9-week executable feed). Refresh
# manually when the audit re-runs upstream.
#
# L4 is the only +ROI lane; the others are surfaced so the user can see
# the full lane library, but they're framed as fallback / context.
_LANE_DEFS = [
    {
        "key": "L4_class",
        "name": "L4 · Class",
        "subtitle": "Clone R1 + career win% ≥ 25",
        "is_primary": True,
        "audit": {"n": 345, "strike_pct": 39.1, "roi_pct": 30.5},
    },
    {
        "key": "L2_mid_favs",
        "name": "L2 · Mid Favs",
        "subtitle": "Clone R1 + market $2–$3",
        "is_primary": False,
        "audit": {"n": 0, "strike_pct": 40.5, "roi_pct": -0.6},
    },
    {
        "key": "L1_short_favs",
        "name": "L1 · Short Favs",
        "subtitle": "Clone R1 + market $1–$2",
        "is_primary": False,
        "audit": {"n": 0, "strike_pct": 56.6, "roi_pct": -7.3},
    },
    {
        "key": "L3_maiden",
        "name": "L3 · Maiden",
        "subtitle": "Clone R1 + maiden race",
        "is_primary": False,
        "audit": {"n": 0, "strike_pct": 33.9, "roi_pct": -0.8},
    },
]


def _is_star(play: dict[str, Any]) -> bool:
    """L4 ∩ Gemini AI_BEST — the +34.7% ROI intersection."""
    return (
        (play.get("lane") == "L4_class" or play.get("bod_source_lane") == "L4_class")
        and play.get("gemini_position") == "AI_BEST"
    )


def _play_to_pick(play: dict[str, Any], race_time: str | None) -> MugPick:
    role = play.get("bod_source") or "primary"
    if role not in ("primary", "fallback", "fallback2", "fallback3"):
        role = "primary"
    # Prefer Clone's fair price over `ai_price` (they're usually the same,
    # but `clone_price` is the canonical OURS signal).
    model_price = play.get("clone_price")
    if model_price is None or (isinstance(model_price, (int, float)) and model_price <= 0):
        model_price = play.get("ai_price")

    return MugPick(
        horse=play.get("horse") or "",
        meeting=play.get("track"),
        race_number=play.get("race_number"),
        tab_number=play.get("tab_number"),
        model_price=model_price,
        market_price=play.get("tab_price"),
        role=role,
        source_lane=play.get("bod_source_lane") or play.get("lane"),
        is_star_tier=_is_star(play),
        win_pct=play.get("win_pct"),
        career_starts=play.get("career_starts"),
        race_time=race_time,
        status="pending",
    )


def build_today(
    curated_payload: dict[str, Any],
    ra_races: list[dict] | None = None,
) -> MugsResponse:
    """Reshape /api/curated → MugsResponse. Best-effort race-time enrichment
    from RA Crawler; missing race_time is fine, picks still render.
    """
    rt_idx = build_race_time_index(ra_races)

    # 1) Best of Day — already capped at 3 upstream.
    bod_raw = curated_payload.get("best_of_day") or []
    best_of_day = [
        _play_to_pick(p, race_time_for(p.get("track"), p.get("race_number"), rt_idx))
        for p in bod_raw
    ]

    # 2) Production lanes. Upstream `lanes` is a dict keyed by lane_key →
    # {name, plays[]}. Pull only the four we surface; skip V/P/S.
    upstream_lanes = curated_payload.get("lanes") or {}
    lanes: list[Lane] = []
    for lane_def in _LANE_DEFS:
        raw = upstream_lanes.get(lane_def["key"]) or {}
        plays = raw.get("plays") or []
        picks = [
            _play_to_pick(p, race_time_for(p.get("track"), p.get("race_number"), rt_idx))
            for p in plays
        ]
        lanes.append(Lane(
            key=lane_def["key"],
            name=lane_def["name"],
            subtitle=lane_def["subtitle"],
            is_primary=lane_def["is_primary"],
            audit=LaneAudit(**lane_def["audit"]),
            picks=picks,
        ))

    return MugsResponse(
        date=curated_payload.get("date"),
        best_of_day=best_of_day,
        lanes=lanes,
        is_stakes_day=bool(curated_payload.get("is_stakes_day", False)),
        metro_pick_count=int(curated_payload.get("metro_pick_count", 0) or 0),
    )
