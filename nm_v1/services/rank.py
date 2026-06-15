"""Tab 3 — Rank (top 3 per race by Clone rank).

Reuse-first: reads the existing /picks `full_card`, takes the top 3 by
clone_rank within each (track, race_no), joins race times from RA Crawler.
Each runner carries an `agreement` count showing 3-voice overlap as a visual
cue — Clone-ranked picks that also lock in with Gemini + SkyNet stand out.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from nm_v1.models import RankMeeting, RankRace, RankResponse, RankRunner
from nm_v1.services.race_times import build_race_time_index, race_time_for
from nm_v1.services.voices import runner_race_id, three_voice_breakdown


def _runner_from_entry(entry: dict[str, Any]) -> RankRunner:
    agreement, _, _ = three_voice_breakdown(entry)
    # Clone's own price preferred; SkyNet's ai_price as fallback.
    model_price = entry.get("clone_price")
    if not isinstance(model_price, (int, float)) or model_price <= 0:
        model_price = entry.get("ai_price")
        if not isinstance(model_price, (int, float)) or model_price <= 0:
            model_price = None
    return RankRunner(
        clone_rank=int(entry["clone_rank"]),
        tab_number=int(entry.get("tab_number") or 0),
        horse=entry.get("horse") or "",
        model_price=model_price,
        market_price=entry.get("tab_price") or None,
        agreement=agreement,
    )


def build_rank(
    picks_payload: dict[str, Any],
    ra_races: list[dict] | None = None,
) -> RankResponse:
    full_card = picks_payload.get("full_card") or {}
    rt_idx = build_race_time_index(ra_races)

    # Group qualifying runners by (track, race_no)
    grouped: dict[str, dict[int, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for track, entries in full_card.items():
        for entry in entries or []:
            clone_rank = entry.get("clone_rank")
            if not isinstance(clone_rank, int) or clone_rank < 1 or clone_rank > 3:
                continue
            race_number = entry.get("race_number")
            if race_number is None:
                continue
            try:
                rn = int(race_number)
            except (TypeError, ValueError):
                continue
            grouped[track][rn].append(entry)

    meetings: list[RankMeeting] = []
    for track in sorted(grouped.keys(), key=str.lower):
        races: list[RankRace] = []
        for race_no in sorted(grouped[track].keys()):
            entries_for_race = sorted(
                grouped[track][race_no],
                key=lambda e: int(e.get("clone_rank") or 99),
            )[:3]
            if not entries_for_race:
                continue

            rid = runner_race_id(entries_for_race[0]) or f"{track.lower().replace(' ', '-')}-R{race_no}"
            races.append(RankRace(
                race_id=rid,
                race_number=race_no,
                race_time=race_time_for(track, race_no, rt_idx),
                runners=[_runner_from_entry(e) for e in entries_for_race],
            ))

        if races:
            meetings.append(RankMeeting(meeting=track, races=races))

    return RankResponse(date=picks_payload.get("date"), meetings=meetings)
