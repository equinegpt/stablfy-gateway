"""Mug ladder computation — pure functions, no I/O.

Takes a raw `/picks` payload from stablfy-social and returns a TodayMugsResponse.
The gateway never passes through bookmaker tipster fields (see README signal
scope) — those fields, if present on the upstream entry, are simply ignored.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from nm_v1.models import Mug, TodayMugsResponse
from nm_v1.services.voices import (
    LEVEL_RANK,
    VOICES_TOTAL,
    model_price,
    runner_race_id,
    voice_breakdown,
)

MELBOURNE = ZoneInfo("Australia/Melbourne")


def _entry_to_mug(entry: dict[str, Any]) -> Mug | None:
    race_id = runner_race_id(entry)
    if race_id is None:
        return None

    level, voices_agree, named, other = voice_breakdown(entry)
    if level is None:
        return None

    return Mug(
        race_id=race_id,
        meeting=entry.get("track") or "",
        race_number=int(entry["race_number"]),
        horse_name=entry.get("horse") or "",
        tab_number=int(entry.get("tab_number") or 0),
        mug_level=level,
        voices_agree=voices_agree,
        named_voices_agree=named,
        other_voices_agree=other,
        model_price=model_price(entry),
        market_price=entry.get("tab_price") or None,
    )


def _sort_key(m: Mug) -> tuple:
    return (
        -LEVEL_RANK[m.mug_level],
        -m.voices_agree,
        m.market_price if m.market_price is not None else 9_999.0,
    )


def build_response(picks_data: dict[str, Any], now: datetime | None = None) -> TodayMugsResponse:
    full_card = picks_data.get("full_card") or {}
    mugs: list[Mug] = []
    for entries in full_card.values():
        for entry in entries or []:
            mug = _entry_to_mug(entry)
            if mug is not None:
                mugs.append(mug)
    mugs.sort(key=_sort_key)

    as_of = (now or datetime.now(MELBOURNE)).isoformat(timespec="seconds")
    return TodayMugsResponse(
        date=picks_data.get("date") or "",
        as_of=as_of,
        voices_total=VOICES_TOTAL,
        mugs=mugs,
    )
