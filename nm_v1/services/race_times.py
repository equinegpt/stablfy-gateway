"""Shared race-time joining helpers.

Used by every tab that joins picks with RA Crawler `/races` (Mugs, AI
Agreement, Rank, Sectionals, ROI). RA Crawler returns DUPLICATE entries per
(track, race_no) — some with `raceTime: null`. We prefer populated values.
Track names are canonicalised via [[track_aliases.canonical_track_name]] so
sponsor prefixes / "Park" suffixes don't break the join.
"""
from __future__ import annotations

from nm_v1.services.track_aliases import canonical_track_name

RaceTimeIndex = dict[tuple[str, int], str | None]


def build_race_time_index(ra_races: list[dict] | None) -> RaceTimeIndex:
    index: RaceTimeIndex = {}
    for entry in ra_races or []:
        track = canonical_track_name(entry.get("track"))
        race_no = entry.get("race_no")
        if not track or race_no is None:
            continue
        try:
            key = (track, int(race_no))
        except (TypeError, ValueError):
            continue
        new_time = entry.get("raceTime")
        existing = index.get(key)
        if existing is None or (new_time and not existing):
            index[key] = new_time
    return index


def race_time_for(track: str | None, race_number: int | None, index: RaceTimeIndex) -> str | None:
    if not track or race_number is None:
        return None
    try:
        return index.get((canonical_track_name(track), int(race_number)))
    except (TypeError, ValueError):
        return None
