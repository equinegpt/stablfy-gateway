"""Unit tests for the race field service. Offline, synthetic payloads."""
from nm_v1.services.races import build_race_detail, build_races_index


def _runner(**overrides):
    base = {
        "meeting_id": 239417,
        "track": "Randwick",
        "race_number": 6,
        "tab_number": 1,
        "horse": "Runner",
        "ai_price": 4.0,
        "tab_price": 4.5,
        "clone_price": 3.8,
        "pfai_price": 4.2,
        "skynet_rank": 5,
        "clone_rank": 5,
        "pfai_rank": 5,
        "gemini_position": "",
        "career_starts": 10,
        "career_wins": 2,
        "win_pct": 20.0,
        "forms_wins_last5": 1,
        "forms_places_last5": 3,
    }
    base.update(overrides)
    return base


def _picks(*runners):
    return {"date": "2026-05-22", "full_card": {"Randwick": list(runners)}}


def test_race_detail_returns_full_field():
    picks = _picks(
        _runner(tab_number=1, horse="A", skynet_rank=1, clone_rank=1, pfai_rank=1,
                gemini_position="AI_BEST"),  # full mug
        _runner(tab_number=2, horse="B", skynet_rank=2, clone_rank=3, pfai_rank=4),  # no mug
        _runner(tab_number=3, horse="C", skynet_rank=1, clone_rank=1, pfai_rank=3),  # splash
    )
    detail = build_race_detail(picks, "239417-R6")
    assert detail is not None
    assert detail.runner_count == 3
    assert detail.mug_count == 2
    assert detail.meeting == "Randwick"
    assert detail.race_number == 6


def test_race_detail_sorts_mugs_first():
    picks = _picks(
        _runner(tab_number=1, horse="NoMug", skynet_rank=4, clone_rank=4, pfai_rank=4),
        _runner(tab_number=2, horse="FullMug", skynet_rank=1, clone_rank=1, pfai_rank=1,
                gemini_position="AI_BEST"),
        _runner(tab_number=3, horse="SplashMug", skynet_rank=1, clone_rank=1, pfai_rank=5),
    )
    detail = build_race_detail(picks, "239417-R6")
    assert [r.horse_name for r in detail.runners] == ["FullMug", "SplashMug", "NoMug"]
    assert detail.runners[0].mug_level == "full"
    assert detail.runners[1].mug_level == "splash"
    assert detail.runners[2].mug_level is None


def test_race_detail_non_mug_runner_fields():
    picks = _picks(_runner(tab_number=7, horse="Plodder", skynet_rank=6,
                           clone_rank=6, pfai_rank=6, career_starts=40, career_wins=3))
    detail = build_race_detail(picks, "239417-R6")
    r = detail.runners[0]
    assert r.mug_level is None
    assert r.voices_agree == 0
    assert r.named_voices_agree == []
    assert r.career_starts == 40
    assert r.career_wins == 3
    assert r.last5_places == 3


def test_race_detail_strips_bookmaker_fields():
    picks = _picks(_runner(
        tab_number=1, skynet_rank=1, clone_rank=1, pfai_rank=1, gemini_position="AI_BEST",
        consensus_agree=2, consensus_sources=["sportsbet", "ladbrokes"],
        bookies_agree=2, tier_suggestion="HARD",
    ))
    detail = build_race_detail(picks, "239417-R6")
    dumped = detail.runners[0].model_dump()
    for forbidden in ("consensus_agree", "consensus_sources", "bookies_agree", "tier_suggestion"):
        assert forbidden not in dumped


def test_race_detail_not_found():
    picks = _picks(_runner())
    assert build_race_detail(picks, "999-R9") is None


def test_races_index_groups_by_meeting_and_counts_mugs():
    picks = {
        "date": "2026-05-22",
        "full_card": {
            "Randwick": [
                _runner(track="Randwick", meeting_id=1, race_number=1, tab_number=1,
                        skynet_rank=1, clone_rank=1, pfai_rank=1, gemini_position="AI_BEST"),
                _runner(track="Randwick", meeting_id=1, race_number=1, tab_number=2,
                        skynet_rank=2, clone_rank=2, pfai_rank=2),
                _runner(track="Randwick", meeting_id=1, race_number=2, tab_number=1,
                        skynet_rank=1, clone_rank=1, pfai_rank=5),  # splash
            ],
            "Flemington": [
                _runner(track="Flemington", meeting_id=2, race_number=1, tab_number=1,
                        skynet_rank=3, clone_rank=3, pfai_rank=3),
            ],
        },
    }
    idx = build_races_index(picks)
    assert [m.meeting for m in idx.meetings] == ["Flemington", "Randwick"]
    rand = next(m for m in idx.meetings if m.meeting == "Randwick")
    assert rand.meeting_id == 1
    assert len(rand.races) == 2
    r1 = next(r for r in rand.races if r.race_number == 1)
    assert r1.runner_count == 2
    assert r1.mug_count == 1
    assert r1.top_mug_level == "full"
    r2 = next(r for r in rand.races if r.race_number == 2)
    assert r2.top_mug_level == "splash"
    flem = next(m for m in idx.meetings if m.meeting == "Flemington")
    assert flem.races[0].mug_count == 0
    assert flem.races[0].top_mug_level is None


def test_races_index_empty():
    idx = build_races_index({"date": "2026-05-22", "full_card": {}})
    assert idx.meetings == []
    assert idx.date == "2026-05-22"
