"""Sectionals.

Two roles served from one PF iReel payload:
  • Race Detail (Tab 2 / Tab 3) reads the most-recent sectional summary fields.
  • Tab 5 (Sectionals) reads the full `runs[]` history per runner + averages.

Both shapes coexist on the same `RunnerSectional` model so consumers pick what
they need without breaking each other. PF iReel sentinel values (>= 900) are
treated as missing and never make it into averages.
"""
from __future__ import annotations

from typing import Any

from nm_v1.models import PastRun, RaceSectionals, RunnerSectional

SENTINEL = 900.0


def parse_in_run(in_run: str | None) -> dict[str, int]:
    """ "finish,3;settling_down,2;m800,2;m400,1;" -> {"finish": 3, ...} """
    out: dict[str, int] = {}
    for segment in (in_run or "").split(";"):
        segment = segment.strip()
        if not segment or "," not in segment:
            continue
        key, _, value = segment.partition(",")
        try:
            out[key.strip()] = int(value.strip())
        except ValueError:
            continue
    return out


def _is_valid(v: Any) -> bool:
    return isinstance(v, (int, float)) and abs(float(v)) < SENTINEL


def _avg(values: list[Any]) -> float | None:
    nums = [float(v) for v in values if _is_valid(v)]
    if not nums:
        return None
    return round(sum(nums) / len(nums), 2)


def _most_recent(sectional_data: list[dict]) -> dict | None:
    if not sectional_data:
        return None
    return max(sectional_data, key=lambda s: s.get("meetingDate") or "")


def _section_to_past_run(section: dict[str, Any]) -> PastRun:
    track = section.get("track") or {}
    return PastRun(
        date=section.get("meetingDate"),
        track=track.get("name"),
        distance=track.get("distance"),
        condition=track.get("trackCondition"),
        last_600m=section.get("last600Time") if _is_valid(section.get("last600Time")) else None,
        last_200m=section.get("last200Time") if _is_valid(section.get("last200Time")) else None,
        last_600_class=section.get("last600Class") if _is_valid(section.get("last600Class")) else None,
    )


def _runner_sectional(runner: dict[str, Any]) -> RunnerSectional:
    sectional_data = runner.get("sectionalData") or []

    # Newest → oldest so iOS can iterate naturally.
    sorted_sections = sorted(
        sectional_data,
        key=lambda s: s.get("meetingDate") or "",
        reverse=True,
    )
    runs = [_section_to_past_run(s) for s in sorted_sections]

    # Most-recent (kept for Race Detail compat)
    recent = sorted_sections[0] if sorted_sections else None
    track = (recent.get("track") or {}) if recent else {}
    in_run = parse_in_run((recent.get("jockey") or {}).get("inRun")) if recent else {}

    return RunnerSectional(
        tab_number=int(runner.get("tabNumber") or 0),
        horse_name=runner.get("horseName") or "",
        last_run_date=(recent or {}).get("meetingDate"),
        last_run_track=track.get("name"),
        last_run_distance=track.get("distance"),
        last_run_condition=track.get("trackCondition"),
        last_600m=(recent or {}).get("last600Time"),
        finish_position=in_run.get("finish"),
        runs=runs,
        avg_last_600m=_avg([s.get("last600Time") for s in sectional_data]),
        avg_last_200m=_avg([s.get("last200Time") for s in sectional_data]),
        avg_last_600_class=_avg([s.get("last600Class") for s in sectional_data]),
    )


def build_sectionals(ireel_payload: dict[str, Any], race_id: str) -> RaceSectionals | None:
    payload = ireel_payload.get("payLoad") or {}
    runners = payload.get("runners") or []
    if not runners:
        return None

    sectionals = [_runner_sectional(r) for r in runners]
    sectionals.sort(key=lambda s: s.tab_number)

    meeting_track = ((payload.get("meeting") or {}).get("track") or {}).get("name") or ""

    return RaceSectionals(
        race_id=race_id,
        meeting=meeting_track,
        race_number=int(payload.get("number") or 0),
        runners=sectionals,
        track_condition=payload.get("trackCondition"),
        race_class=payload.get("raceClass"),
        distance=payload.get("distance"),
        race_name=payload.get("name"),
    )
