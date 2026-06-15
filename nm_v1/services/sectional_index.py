"""Sectionals tab — date-keyed meetings/races index.

Builds a meetings → races list from RA Crawler `/races` filtered to a date.
Races without a numeric `meetingId` are dropped (PF iReel needs it to call
the per-race sectional endpoint).
"""
from __future__ import annotations

from typing import Any

from nm_v1.models import SectionalMeeting, SectionalRace, SectionalRacesResponse


def build_sectional_meetings(ra_races: list[dict] | None, date: str) -> SectionalRacesResponse:
    by_meeting: dict[int, dict[str, Any]] = {}

    for race in ra_races or []:
        meeting_id = race.get("meetingId")
        if meeting_id is None:
            continue
        try:
            mid = int(meeting_id)
        except (TypeError, ValueError):
            continue

        race_date = (race.get("date") or "")[:10]
        if not race_date.startswith(date[:10]):
            continue

        try:
            race_no = int(race.get("race_no"))
        except (TypeError, ValueError):
            continue

        track = race.get("track") or ""

        slot = by_meeting.setdefault(mid, {
            "meeting_id": mid,
            "track": track,
            "state": race.get("state"),
            "date": race_date,
            "races": [],
        })
        # Prefer non-empty fields from later rows (RA Crawler dupes some entries).
        if not slot.get("state") and race.get("state"):
            slot["state"] = race.get("state")
        # Skip duplicate race_no within the same meeting.
        if any(r.race_number == race_no for r in slot["races"]):
            # Update raceTime if the new entry has it and the existing doesn't
            for existing in slot["races"]:
                if existing.race_number == race_no and not existing.race_time and race.get("raceTime"):
                    existing.race_time = race.get("raceTime")
            continue
        slot["races"].append(SectionalRace(
            race_id=f"{mid}-R{race_no}",
            meeting_id=mid,
            race_number=race_no,
            description=race.get("description"),
            distance=race.get("distance_m"),
            race_time=race.get("raceTime"),
        ))

    meetings: list[SectionalMeeting] = []
    for slot in sorted(by_meeting.values(), key=lambda m: (m.get("track") or "").lower()):
        slot["races"].sort(key=lambda r: r.race_number)
        meetings.append(SectionalMeeting(**slot))

    return SectionalRacesResponse(date=date, meetings=meetings)
