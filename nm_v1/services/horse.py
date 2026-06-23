"""Horse deep-dive transforms — pure functions, no I/O.

racing-db `/api/v1/horse/{code}` returns the full profile (career, form,
track/condition/distance breakdowns, jockey/trainer rolling stats) — we just
pass it through into Pydantic models.
"""
from __future__ import annotations

from typing import Any

from nm_v1.models import (
    BiomechScore,
    BiomechSireContext,
    CareerStats,
    ConditionStat,
    DistanceStat,
    HorseDeepDive,
    HorseInfo,
    HorseStart,
    PersonStats,
    SaleHistoryEntry,
    StatBreakdown,
    TrackStat,
)


def pick_best_match(name: str, candidates: list[dict]) -> dict | None:
    if not candidates:
        return None
    target = name.strip().lower()
    exact = [c for c in candidates if (c.get("name") or "").strip().lower() == target]
    pool = exact or candidates
    return max(pool, key=lambda c: c.get("career_starts") or c.get("career_wins") or 0)


def build_deep_dive(record: dict[str, Any], form_limit: int = 10) -> HorseDeepDive | None:
    horse = record.get("horse") or {}
    code = horse.get("horse_code")
    if not code:
        return None

    form_in = record.get("form") or []
    form = [
        HorseStart(
            race_date=f.get("race_date"),
            track=f.get("track"),
            state=f.get("state"),
            distance=f.get("distance"),
            race_class=f.get("race_class"),
            track_condition=f.get("track_condition"),
            position=f.get("position"),
            field_size=f.get("field_size"),
            margin=f.get("margin"),
            barrier=f.get("barrier"),
            weight=f.get("weight"),
            handicap_rating=f.get("handicap_rating"),
            jockey=f.get("jockey"),
            odds=f.get("odds_closing"),
            last_600m=f.get("last_600m"),
        )
        for f in form_in[:form_limit]
    ]

    return HorseDeepDive(
        horse=HorseInfo(
            horse_code=str(code),
            name=horse.get("name") or "",
            sex=horse.get("sex"),
            colour=horse.get("colour"),
            dob=horse.get("dob"),
            country=horse.get("country"),
            sire_name=horse.get("sire_name"),
            dam_name=horse.get("dam_name"),
            sire_of_dam=horse.get("sire_of_dam"),
            trainer_name=horse.get("trainer_name"),
            owner=horse.get("owner"),
        ),
        career=_career(record.get("career") or {}),
        form=form,
        track_stats=[_track(s) for s in (record.get("track_stats") or [])],
        condition_stats=[_condition(s) for s in (record.get("condition_stats") or [])],
        distance_stats=[_distance(s) for s in (record.get("distance_stats") or [])],
        jockey_stats=_person(record.get("jockey_stats")),
        trainer_stats=_person(record.get("trainer_stats")),
        sale_history=[_sale(s) for s in (record.get("sale_history") or [])],
        biomech=_biomech(record.get("biomech")),
        biomech_sire_context=_biomech_sire(record.get("biomech_sire_context")),
    )


def _career(c: dict) -> CareerStats:
    return CareerStats(
        starts=c.get("starts") or 0,
        wins=c.get("wins") or 0,
        seconds=c.get("seconds") or 0,
        thirds=c.get("thirds") or 0,
        prizemoney=c.get("prizemoney") or 0.0,
        best_rating=c.get("best_rating"),
    )


def _track(s: dict) -> TrackStat:
    return TrackStat(
        track=s.get("track") or "",
        distance=s.get("distance"),
        runs=s.get("runs") or 0,
        wins=s.get("wins") or 0,
        places=s.get("places") or 0,
    )


def _condition(s: dict) -> ConditionStat:
    return ConditionStat(
        condition=s.get("condition") or "",
        runs=s.get("runs") or 0,
        wins=s.get("wins") or 0,
        places=s.get("places") or 0,
    )


def _distance(s: dict) -> DistanceStat:
    return DistanceStat(
        category=s.get("category") or "",
        runs=s.get("runs") or 0,
        wins=s.get("wins") or 0,
        places=s.get("places") or 0,
    )


def _person(p: dict | None) -> PersonStats | None:
    if not p:
        return None
    return PersonStats(
        name=p.get("name") or "",
        this_track=_breakdown(p.get("this_track")),
        this_distance=_breakdown(p.get("this_distance")),
        last_30_days=_breakdown(p.get("last_30_days")),
    )


def _breakdown(b: dict | None) -> StatBreakdown:
    if not b:
        return StatBreakdown()
    return StatBreakdown(starts=b.get("starts") or 0, wins=b.get("wins") or 0)


def _sale(s: dict) -> SaleHistoryEntry:
    return SaleHistoryEntry(
        sale_code=s.get("sale_code") or "",
        sale_house=s.get("sale_house"),
        sale_name=s.get("sale_name"),
        sale_year=s.get("sale_year"),
        sale_type=s.get("sale_type"),
        lot_number=s.get("lot_number"),
        price=s.get("price"),
        sale_status=s.get("sale_status"),
        buyer=s.get("buyer"),
        vendor=s.get("vendor"),
        match_method=s.get("match_method"),
        match_confidence=s.get("match_confidence"),
    )


def _biomech(b: dict | None) -> BiomechScore | None:
    if not b:
        return None
    return BiomechScore(
        sale_code=b.get("sale_code"),
        lot_number=b.get("lot_number"),
        tier=b.get("tier"),
        net=b.get("net"),
        n_out=b.get("n_out"),
        n_under=b.get("n_under"),
        n_neutral=b.get("n_neutral"),
        n_trusted_sections=b.get("n_trusted_sections"),
        total_trusted_seconds=b.get("total_trusted_seconds"),
        scorecard_version=b.get("scorecard_version"),
        scored_at=b.get("scored_at"),
    )


def _biomech_sire(c: dict | None) -> BiomechSireContext | None:
    if not c:
        return None
    return BiomechSireContext(
        n_scored=c.get("n_scored") or 0,
        median_net=c.get("median_net"),
        pct_top=c.get("pct_top"),
        pct_bot=c.get("pct_bot"),
    )
