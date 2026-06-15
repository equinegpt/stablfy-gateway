"""Tab 2 — AI Agreement.

3-voice convergence (Clone + Gemini + SkyNet) computed from the existing
stablfy-social /picks `full_card`. SkyNet is anonymised as `other_voices`
(per [[feedback_no_mugs_signal_sources]]). pfai is DROPPED from this view.

Returns a flat list of qualifying runners (agreement >= 2). iOS handles the
filter/sort/grouping client-side via AppStorage so changes are snappy.
"""
from __future__ import annotations

from typing import Any

from nm_v1.models import AgreementRunner, AgreementsResponse
from nm_v1.services.race_times import build_race_time_index, race_time_for
from nm_v1.services.voices import runner_race_id, three_voice_breakdown


def _model_price(entry: dict[str, Any]) -> float | None:
    """Average of the available model prices (SkyNet's `ai_price` + Clone's
    `clone_price`). Gemini doesn't give a price."""
    candidates = [entry.get("ai_price"), entry.get("clone_price")]
    nums = [v for v in candidates if isinstance(v, (int, float)) and v > 0]
    if not nums:
        return None
    return round(sum(nums) / len(nums), 2)


def build_agreements(
    picks_payload: dict[str, Any],
    ra_races: list[dict] | None = None,
) -> AgreementsResponse:
    full_card = picks_payload.get("full_card") or {}
    rt_idx = build_race_time_index(ra_races)

    runners: list[AgreementRunner] = []
    for entries in full_card.values():
        for entry in entries or []:
            agreement, named, other = three_voice_breakdown(entry)
            if agreement < 2:
                continue
            race_number = entry.get("race_number")
            if race_number is None:
                continue
            rid = runner_race_id(entry)
            if rid is None:
                continue

            runners.append(AgreementRunner(
                race_id=rid,
                meeting=entry.get("track") or "",
                race_number=int(race_number),
                race_time=race_time_for(entry.get("track"), race_number, rt_idx),
                tab_number=int(entry.get("tab_number") or 0),
                horse=entry.get("horse") or "",
                agreement=agreement,
                named_voices=named,
                other_voices=other,
                model_price=_model_price(entry),
                market_price=entry.get("tab_price") or None,
            ))

    runners.sort(key=lambda r: (-r.agreement, r.meeting.lower(), r.race_number, r.tab_number))

    return AgreementsResponse(
        date=picks_payload.get("date"),
        runners=runners,
    )
