"""Speed map computation — turns the PF Speedmaps payload into banded runners.

PF gives each runner a `settle` (predicted settling position, 1 = leads) and a
`speed` rating. Runners with no early-speed data come back as speed=0 / settle=25
(a sentinel) — we surface those as "unknown" rather than pretending they settle
at the back.
"""
from __future__ import annotations

from typing import Any

from nm_v1.models import RaceSpeedmap, SettleBand, SpeedmapRunner

SENTINEL_SETTLE = 20

_BAND_ORDER: dict[SettleBand, int] = {
    "lead": 0,
    "on_pace": 1,
    "midfield": 2,
    "back": 3,
    "unknown": 4,
}


def settle_band(settle: int | None, speed: int | None) -> SettleBand:
    if not speed or settle is None or settle >= SENTINEL_SETTLE:
        return "unknown"
    if settle <= 1:
        return "lead"
    if settle <= 3:
        return "on_pace"
    if settle <= 6:
        return "midfield"
    return "back"


def build_speedmap(pf_payload: dict[str, Any], race_id: str) -> RaceSpeedmap | None:
    payload = pf_payload.get("payLoad") or []
    if not payload:
        return None
    race = payload[0]
    items = race.get("items") or []

    runners: list[SpeedmapRunner] = []
    for it in items:
        settle = it.get("settle")
        speed = it.get("speed")
        band = settle_band(settle, speed)
        real_settle = settle if band != "unknown" else None
        runners.append(SpeedmapRunner(
            tab_number=int(it.get("tabNo") or 0),
            horse_name=it.get("runnerName") or "",
            settle=real_settle,
            band=band,
            barrier=it.get("barrier"),
            rated_run_style=int(it.get("ratedRunStyle") or 0),
        ))

    runners.sort(key=lambda r: (
        _BAND_ORDER[r.band],
        r.settle if r.settle is not None else 99,
        r.tab_number,
    ))

    return RaceSpeedmap(
        race_id=race_id,
        meeting=race.get("track") or "",
        race_number=int(race.get("raceNo") or 0),
        runners=runners,
    )
