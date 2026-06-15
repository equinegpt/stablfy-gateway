"""Shared primitives for reading the 4 model voices off a /picks runner entry.

Voices: SkyNet, Clone, pfai, Gemini. Only Gemini and Clone are surfaced by
name downstream; SkyNet and pfai are anonymised as "other AI models". Bookmaker
fields (consensus_*, bookies_agree, tier_suggestion) are never read here.
"""
from __future__ import annotations

from typing import Any

from nm_v1.models import MugLevel

VOICES_TOTAL = 4
LEVEL_RANK: dict[MugLevel, int] = {"full": 3, "half": 2, "splash": 1}


def classify(agree_count: int) -> MugLevel | None:
    if agree_count >= 4:
        return "full"
    if agree_count == 3:
        return "half"
    if agree_count == 2:
        return "splash"
    return None


def avg_price(values: list[float | None]) -> float | None:
    vals = [v for v in values if isinstance(v, (int, float)) and v > 0]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 2)


def model_price(entry: dict[str, Any]) -> float | None:
    return avg_price([
        entry.get("ai_price"),
        entry.get("clone_price"),
        entry.get("pfai_price"),
    ])


def runner_race_id(entry: dict[str, Any]) -> str | None:
    race_number = entry.get("race_number")
    if race_number is None:
        return None
    meeting_id = entry.get("meeting_id")
    track = entry.get("track") or ""
    prefix = str(meeting_id) if meeting_id is not None else track.lower().replace(" ", "-")
    return f"{prefix}-R{race_number}"


def parse_race_id(race_id: str) -> tuple[int, int] | None:
    """Parse "239793-R1" -> (meeting_id=239793, race_number=1).

    Returns None when the race_id has a non-numeric (track-slug) prefix, which
    means there's no PF meeting_id to call PF endpoints with.
    """
    prefix, sep, rno = race_id.rpartition("-R")
    if not sep or not prefix.isdigit() or not rno.isdigit():
        return None
    return int(prefix), int(rno)


def voice_breakdown(entry: dict[str, Any]) -> tuple[MugLevel | None, int, list[str], int]:
    """Returns (mug_level, voices_agree, named_voices_agree, other_voices_agree)."""
    voices = {
        "skynet": entry.get("skynet_rank") == 1,
        "clone": entry.get("clone_rank") == 1,
        "pfai": entry.get("pfai_rank") == 1,
        "gemini": entry.get("gemini_position") == "AI_BEST",
    }
    voices_agree = sum(voices.values())
    level = classify(voices_agree)
    named = [v for v in ("gemini", "clone") if voices[v]]
    other = sum(1 for v in ("skynet", "pfai") if voices[v])
    return level, voices_agree, named, other


def three_voice_breakdown(entry: dict[str, Any]) -> tuple[int, list[str], int]:
    """3-voice convergence used by AI Agreement (Tab 2) and Rank's overlap badge.

    Clone + Gemini + SkyNet. pfai dropped per the 2026-06-15 naming rules.
    Returns (agreement, named_voices, other_voices).
    """
    voices = {
        "clone":  entry.get("clone_rank") == 1,
        "gemini": entry.get("gemini_position") == "AI_BEST",
        "skynet": entry.get("skynet_rank") == 1,
    }
    agreement = sum(voices.values())
    named = [v for v in ("gemini", "clone") if voices[v]]
    other = 1 if voices["skynet"] else 0
    return agreement, named, other
