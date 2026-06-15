"""Unit tests for the horse deep-dive transforms. Offline, synthetic payloads."""
from nm_v1.services.horse import build_deep_dive, pick_best_match


def test_pick_best_match_prefers_exact_name():
    candidates = [
        {"horse_code": "1", "name": "SYLPHEED", "career_starts": 20},
        {"horse_code": "2", "name": "SYLPH", "career_starts": 9},
    ]
    match = pick_best_match("Sylph", candidates)
    assert match["horse_code"] == "2"


def test_pick_best_match_breaks_ties_by_career_starts():
    candidates = [
        {"horse_code": "1", "name": "ZORB", "career_starts": 3},
        {"horse_code": "2", "name": "ZORB", "career_starts": 41},
    ]
    match = pick_best_match("ZORB", candidates)
    assert match["horse_code"] == "2"


def test_pick_best_match_falls_back_to_candidates_when_no_exact():
    candidates = [{"horse_code": "9", "name": "SOMETHING ELSE", "career_starts": 5}]
    match = pick_best_match("Nonexistent", candidates)
    assert match["horse_code"] == "9"


def test_pick_best_match_empty():
    assert pick_best_match("Anything", []) is None


def _record():
    return {
        "horse": {
            "horse_code": "1709401920", "name": "SYLPH", "sex": "Filly",
            "colour": "Bay", "dob": "2022-09-23", "country": "AUS",
            "sire_name": "I AM INVINCIBLE", "dam_name": "NOONDIE",
            "sire_of_dam": "REDOUTE'S CHOICE",
            "trainer_name": "Michael Freedman",
        },
        "career": {
            "starts": 9, "wins": 0, "seconds": 3, "thirds": 3,
            "prizemoney": 371325.0, "best_rating": None,
        },
        "form": [
            {"race_date": "2026-05-09", "track": "Gold Coast", "distance": 1200,
             "race_class": "Group 3", "track_condition": "Good4", "position": 7,
             "field_size": 14, "margin": 3.95, "jockey": "Tommy Berry",
             "barrier": 9, "weight": 56.0, "odds_closing": 7.5, "last_600m": 33.88},
            {"race_date": "2026-04-25", "track": "Flemington", "distance": 1000,
             "position": 3, "field_size": 12, "odds_closing": 5.5},
        ],
        "track_stats": [
            {"track": "Gold Coast", "distance": 1200, "runs": 3, "wins": 0, "places": 1},
        ],
        "condition_stats": [
            {"condition": "Good4", "runs": 5, "wins": 0, "places": 3},
        ],
        "distance_stats": [
            {"category": "Sprint", "runs": 6, "wins": 0, "places": 3},
        ],
        "jockey_stats": {
            "name": "Tommy Berry",
            "this_track": {"starts": 120, "wins": 28},
            "this_distance": {"starts": 400, "wins": 70},
            "last_30_days": {"starts": 35, "wins": 6},
        },
        "trainer_stats": {
            "name": "Michael Freedman",
            "this_track": {"starts": 60, "wins": 12},
            "this_distance": {"starts": 240, "wins": 45},
            "last_30_days": {"starts": 80, "wins": 9},
        },
    }


def test_build_deep_dive_maps_profile_and_form():
    dd = build_deep_dive(_record())
    assert dd is not None
    assert dd.horse.horse_code == "1709401920"
    assert dd.horse.name == "SYLPH"
    assert dd.horse.sire_name == "I AM INVINCIBLE"
    assert dd.horse.trainer_name == "Michael Freedman"
    assert dd.career.prizemoney == 371325.0
    assert dd.career.starts == 9
    assert len(dd.form) == 2
    first = dd.form[0]
    assert first.track == "Gold Coast"
    assert first.position == 7
    assert first.field_size == 14
    assert first.odds == 7.5
    assert first.last_600m == 33.88
    assert first.barrier == 9


def test_build_deep_dive_carries_stats_blocks():
    dd = build_deep_dive(_record())
    assert dd is not None
    assert dd.jockey_stats is not None
    assert dd.jockey_stats.name == "Tommy Berry"
    assert dd.jockey_stats.this_track.starts == 120
    assert dd.trainer_stats is not None
    assert dd.trainer_stats.last_30_days.wins == 9
    assert dd.condition_stats[0].condition == "Good4"
    assert dd.distance_stats[0].category == "Sprint"


def test_build_deep_dive_limits_starts():
    rec = _record()
    rec["form"] = rec["form"] * 10  # 20 starts
    dd = build_deep_dive(rec, form_limit=6)
    assert len(dd.form) == 6


def test_build_deep_dive_no_horse_code():
    assert build_deep_dive({"horse": {}, "form": []}) is None
    assert build_deep_dive({}) is None
