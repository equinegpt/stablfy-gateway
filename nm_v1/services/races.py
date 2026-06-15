"""Race field computation — pure functions, no I/O.

Builds race index + per-race field views from the same /picks payload the Mug
ladder uses. Reuses the shared voice helpers so a runner's mug status here is
identical to the Today tab. Bookmaker fields are never read.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from nm_v1.models import (
    MeetingSummary,
    RaceDetail,
    RaceRunner,
    RacesIndexResponse,
    RaceSummary,
)
from nm_v1.services.voices import (
    LEVEL_RANK,
    model_price,
    runner_race_id,
    voice_breakdown,
)

MELBOURNE = ZoneInfo("Australia/Melbourne")


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _all_entries(picks_data: dict[str, Any]) -> list[dict]:
    full_card = picks_data.get("full_card") or {}
    out: list[dict] = []
    for entries in full_card.values():
        out.extend(entries or [])
    return out


def _entry_to_runner(entry: dict[str, Any]) -> RaceRunner | None:
    tab = entry.get("tab_number")
    if tab is None:
        return None
    level, voices_agree, named, other = voice_breakdown(entry)
    return RaceRunner(
        tab_number=int(tab),
        horse_name=entry.get("horse") or "",
        mug_level=level,
        voices_agree=voices_agree,
        named_voices_agree=named,
        other_voices_agree=other,
        model_price=model_price(entry),
        market_price=entry.get("tab_price") or None,
        career_starts=entry.get("career_starts"),
        career_wins=entry.get("career_wins"),
        win_pct=entry.get("win_pct"),
        last5_wins=entry.get("forms_wins_last5"),
        last5_places=entry.get("forms_places_last5"),
    )


def _runner_sort_key(r: RaceRunner) -> tuple:
    return (
        -LEVEL_RANK.get(r.mug_level, 0),
        -r.voices_agree,
        r.model_price if r.model_price is not None else 9_999.0,
        r.tab_number,
    )


def build_race_detail(picks_data: dict[str, Any], race_id: str) -> RaceDetail | None:
    entries = [e for e in _all_entries(picks_data) if runner_race_id(e) == race_id]
    if not entries:
        return None

    runners = [r for e in entries if (r := _entry_to_runner(e)) is not None]
    runners.sort(key=_runner_sort_key)
    mug_count = sum(1 for r in runners if r.mug_level is not None)

    first = entries[0]
    return RaceDetail(
        race_id=race_id,
        meeting=first.get("track") or "",
        race_number=int(first["race_number"]),
        runner_count=len(runners),
        mug_count=mug_count,
        runners=runners,
    )


def build_races_index(picks_data: dict[str, Any], now: datetime | None = None) -> RacesIndexResponse:
    full_card = picks_data.get("full_card") or {}
    meetings: list[MeetingSummary] = []

    for track, entries in full_card.items():
        entries = entries or []
        by_race: dict[int, list] = {}
        meeting_id: Any = None
        for e in entries:
            rn = _safe_int(e.get("race_number"))
            if rn is None:
                continue
            by_race.setdefault(rn, []).append(e)
            if meeting_id is None:
                meeting_id = e.get("meeting_id")

        races: list[RaceSummary] = []
        for rn in sorted(by_race):
            rentries = by_race[rn]
            mug_levels = [lv for e in rentries if (lv := voice_breakdown(e)[0]) is not None]
            top = max(mug_levels, key=lambda lv: LEVEL_RANK[lv]) if mug_levels else None
            races.append(RaceSummary(
                race_id=runner_race_id(rentries[0]) or f"{track}-R{rn}",
                race_number=rn,
                runner_count=len(rentries),
                mug_count=len(mug_levels),
                top_mug_level=top,
            ))

        meetings.append(MeetingSummary(
            meeting=track,
            meeting_id=_safe_int(meeting_id),
            races=races,
        ))

    meetings.sort(key=lambda m: m.meeting)
    as_of = (now or datetime.now(MELBOURNE)).isoformat(timespec="seconds")
    return RacesIndexResponse(
        date=picks_data.get("date") or "",
        as_of=as_of,
        meetings=meetings,
    )
