"""Tests for the Rank (Tab 3) builder — top 3 per race by Clone rank."""
from nm_v1.services.rank import build_rank


def _runner(track="Randwick", race_number=6, tab=1, horse="Brutalina",
            clone_rank=1, ai_price=3.5, clone_price=3.8, tab_price=4.5,
            meeting_id=239417,
            skynet_rank=None, gemini_position=""):
    return {
        "meeting_id": meeting_id, "track": track, "race_number": race_number,
        "tab_number": tab, "horse": horse,
        "clone_rank": clone_rank, "clone_price": clone_price,
        "ai_price": ai_price, "tab_price": tab_price,
        "skynet_rank": skynet_rank, "gemini_position": gemini_position,
    }


def _picks(*runners, full_card_track="Randwick"):
    return {"date": "2026-06-15", "full_card": {full_card_track: list(runners)}}


def test_top_3_per_race_by_clone_rank():
    picks = _picks(
        _runner(tab=4, horse="One",   clone_rank=1),
        _runner(tab=7, horse="Two",   clone_rank=2),
        _runner(tab=9, horse="Three", clone_rank=3),
        _runner(tab=2, horse="Four",  clone_rank=4),
        _runner(tab=5, horse="Five",  clone_rank=5),
    )
    resp = build_rank(picks)
    assert len(resp.meetings) == 1
    race = resp.meetings[0].races[0]
    assert [r.horse for r in race.runners] == ["One", "Two", "Three"]
    assert [r.clone_rank for r in race.runners] == [1, 2, 3]


def test_runners_outside_top_3_ignored():
    picks = _picks(
        _runner(horse="Cloned1", clone_rank=1),
        _runner(tab=2, horse="Cloned4", clone_rank=4),
        _runner(tab=3, horse="NoClone", clone_rank=None),
    )
    resp = build_rank(picks)
    race = resp.meetings[0].races[0]
    assert [r.horse for r in race.runners] == ["Cloned1"]


def test_agreement_overlap_flag():
    """Rank rows carry the 3-voice agreement count for visual overlap.

    Each voice only votes when its rank/position == 1, so a Clone-2 horse
    can still hit agreement 2 if SkyNet and Gemini both back it.
    """
    picks = _picks(
        _runner(tab=4, horse="Triple", clone_rank=1, skynet_rank=1, gemini_position="AI_BEST"),
        _runner(tab=2, horse="Double", clone_rank=2, skynet_rank=1, gemini_position="AI_BEST"),
        _runner(tab=5, horse="Single", clone_rank=3, skynet_rank=1, gemini_position=""),
    )
    resp = build_rank(picks)
    runners = resp.meetings[0].races[0].runners
    by_horse = {r.horse: r.agreement for r in runners}
    assert by_horse["Triple"] == 3
    assert by_horse["Double"] == 2
    assert by_horse["Single"] == 1


def test_multiple_meetings_and_races():
    picks = {
        "date": "2026-06-15",
        "full_card": {
            "Randwick": [
                _runner(track="Randwick", race_number=1, tab=1, horse="R1H1", clone_rank=1),
                _runner(track="Randwick", race_number=1, tab=2, horse="R1H2", clone_rank=2),
                _runner(track="Randwick", race_number=2, tab=4, horse="R2H1", clone_rank=1),
            ],
            "Caulfield": [
                _runner(track="Caulfield", race_number=3, tab=7, horse="C3H1", clone_rank=1),
            ],
        },
    }
    resp = build_rank(picks)
    assert [m.meeting for m in resp.meetings] == ["Caulfield", "Randwick"]
    randwick = next(m for m in resp.meetings if m.meeting == "Randwick")
    assert [r.race_number for r in randwick.races] == [1, 2]


def test_race_time_joined():
    picks = _picks(_runner(clone_rank=1))
    ra = [{"track": "Randwick", "race_no": 6, "raceTime": "14:35"}]
    resp = build_rank(picks, ra)
    assert resp.meetings[0].races[0].race_time == "14:35"


def test_market_price_from_tab_price():
    picks = _picks(_runner(clone_rank=1, tab_price=4.5))
    resp = build_rank(picks)
    assert resp.meetings[0].races[0].runners[0].market_price == 4.5


def test_falls_back_to_ai_price_when_clone_price_missing():
    picks = _picks(_runner(clone_rank=1, clone_price=None, ai_price=3.5))
    resp = build_rank(picks)
    assert resp.meetings[0].races[0].runners[0].model_price == 3.5


def test_empty_full_card():
    resp = build_rank({"date": "2026-06-15"}, [])
    assert resp.meetings == []
    assert resp.date == "2026-06-15"
