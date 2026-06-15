"""Tab 1 (Mugs) — two BoD lanes with rolling SR/ROI summaries.

Picks come from `/api/curated` (no auth). Per-lane window summaries are scraped
from `/best-of-day` HTML — no JSON source for those numbers exists yet. Race
times come from RA Crawler. Picks are PENDING (today's haven't run); settled
numbers live on the lane summary.
"""
from __future__ import annotations

from typing import Any

from nm_v1.models import BodLane, BodLaneSummary, MugPick, MugsResponse
from nm_v1.services.race_times import build_race_time_index, race_time_for


_LANES = [
    {
        "key": "v1",
        "name": "Best of Day",
        "subtitle": "Live · cohort-filtered",
        "field": "best_of_day",
    },
    {
        "key": "v2",
        "name": "Career Class",
        "subtitle": "Experimental · paper trial",
        "field": "best_of_day_v2_career",
    },
]


def _avg_price(values: list[Any]) -> float | None:
    nums = [float(v) for v in values if isinstance(v, (int, float)) and v > 0]
    if not nums:
        return None
    return round(sum(nums) / len(nums), 2)


def _entry_to_pick(entry: dict[str, Any], race_time: str | None) -> MugPick:
    role = entry.get("bod_source") or "primary"
    return MugPick(
        horse=entry.get("horse") or "",
        meeting=entry.get("track"),
        race_number=entry.get("race_number"),
        tab_number=entry.get("tab_number"),
        model_price=_avg_price([entry.get("ai_price"), entry.get("clone_price")]),
        market_price=entry.get("tab_price"),
        role=role if role in ("primary", "fallback") else "primary",
        race_time=race_time,
        status="pending",
    )


def build_today(
    curated_payload: dict[str, Any],
    ra_races: list[dict] | None = None,
    bod_summaries: dict[str, dict[str, Any]] | None = None,
    days: int = 30,
) -> MugsResponse:
    """Builds the two-lane MugsResponse.

    `bod_summaries` is the scraped result from [[bod_summary.parse_bod_summaries]]
    — `{"v1": {...}, "v2": {...}}`. Pass `{}` (or None) if scraping failed: the
    response still serves today's picks with zero-summary lanes so the iOS app
    degrades gracefully rather than 500-ing.
    """
    bod_summaries = bod_summaries or {}
    rt_idx = build_race_time_index(ra_races)
    lanes: list[BodLane] = []

    for lane_def in _LANES:
        raw_picks = curated_payload.get(lane_def["field"]) or []
        picks = [
            _entry_to_pick(
                raw,
                race_time_for(raw.get("track"), raw.get("race_number"), rt_idx),
            )
            for raw in raw_picks
        ]
        summary_data = bod_summaries.get(lane_def["key"]) or {}
        summary = BodLaneSummary(days=days, **summary_data)
        lanes.append(BodLane(
            key=lane_def["key"],
            name=lane_def["name"],
            subtitle=lane_def["subtitle"],
            summary=summary,
            picks=picks,
        ))

    return MugsResponse(date=curated_payload.get("date"), lanes=lanes)
