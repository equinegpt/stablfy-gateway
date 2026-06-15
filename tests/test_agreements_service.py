"""Tests for the AI Agreement (Tab 2) builder — 3-voice convergence."""
from nm_v1.services.agreements import build_agreements


def _runner(track="Randwick", race_number=6, tab=4, horse="Brutalina",
            meeting_id=239417, ai_price=3.4, clone_price=3.8, tab_price=4.5,
            skynet_rank=None, clone_rank=None, gemini_position=""):
    return {
        "meeting_id": meeting_id, "track": track, "race_number": race_number,
        "tab_number": tab, "horse": horse,
        "ai_price": ai_price, "clone_price": clone_price, "tab_price": tab_price,
        "skynet_rank": skynet_rank, "clone_rank": clone_rank,
        "gemini_position": gemini_position,
    }


def _picks(*runners, full_card_track="Randwick"):
    return {"date": "2026-06-15", "full_card": {full_card_track: list(runners)}}


def test_three_voice_all_agree():
    picks = _picks(_runner(skynet_rank=1, clone_rank=1, gemini_position="AI_BEST"))
    resp = build_agreements(picks)
    assert len(resp.runners) == 1
    r = resp.runners[0]
    assert r.agreement == 3
    assert set(r.named_voices) == {"gemini", "clone"}
    assert r.other_voices == 1  # SkyNet anonymised


def test_three_voice_two_of_three_clone_gemini():
    picks = _picks(_runner(skynet_rank=2, clone_rank=1, gemini_position="AI_BEST"))
    resp = build_agreements(picks)
    assert resp.runners[0].agreement == 2
    assert set(resp.runners[0].named_voices) == {"gemini", "clone"}
    assert resp.runners[0].other_voices == 0


def test_three_voice_two_of_three_skynet_only_named():
    picks = _picks(_runner(skynet_rank=1, clone_rank=1, gemini_position="DANGER"))
    resp = build_agreements(picks)
    assert resp.runners[0].agreement == 2
    assert resp.runners[0].named_voices == ["clone"]
    assert resp.runners[0].other_voices == 1


def test_only_two_or_more_included():
    picks = _picks(
        _runner(horse="Solo", skynet_rank=1, clone_rank=2, gemini_position=""),
        _runner(horse="Triple", tab=5, skynet_rank=1, clone_rank=1, gemini_position="AI_BEST"),
    )
    resp = build_agreements(picks)
    horses = [r.horse for r in resp.runners]
    assert "Solo" not in horses
    assert "Triple" in horses


def test_pfai_not_a_voice():
    """pfai is explicitly dropped from the 3-voice definition."""
    raw = _runner(skynet_rank=4, clone_rank=4, gemini_position="DANGER")
    raw["pfai_rank"] = 1
    picks = _picks(raw)
    resp = build_agreements(picks)
    assert resp.runners == []  # pfai==1 doesn't qualify


def test_strips_bookmaker_fields_by_construction():
    """AgreementRunner has no bookies_agree / consensus_* / tier — Pydantic strips."""
    raw = _runner(skynet_rank=1, clone_rank=1, gemini_position="AI_BEST")
    raw.update({
        "consensus_agree": 4, "consensus_sources": ["sportsbet", "ladbrokes"],
        "bookies_agree": 2, "tier_suggestion": "HARD",
    })
    resp = build_agreements(_picks(raw))
    dumped = resp.runners[0].model_dump()
    for forbidden in ("consensus_agree", "consensus_sources", "bookies_agree", "tier_suggestion"):
        assert forbidden not in dumped


def test_sort_full_agreement_first():
    picks = _picks(
        _runner(horse="Half", tab=2, skynet_rank=1, clone_rank=2, gemini_position="AI_BEST"),
        _runner(horse="Full", tab=4, skynet_rank=1, clone_rank=1, gemini_position="AI_BEST"),
    )
    resp = build_agreements(picks)
    assert [r.horse for r in resp.runners] == ["Full", "Half"]


def test_joins_race_time_from_ra():
    picks = _picks(_runner(skynet_rank=1, clone_rank=1, gemini_position="AI_BEST"))
    ra = [{"track": "Randwick", "race_no": 6, "raceTime": "14:35"}]
    resp = build_agreements(picks, ra)
    assert resp.runners[0].race_time == "14:35"


def test_model_price_averages_skynet_and_clone():
    picks = _picks(_runner(
        ai_price=4.0, clone_price=6.0,
        skynet_rank=1, clone_rank=1, gemini_position="AI_BEST",
    ))
    resp = build_agreements(picks)
    assert resp.runners[0].model_price == 5.0


def test_empty_full_card():
    resp = build_agreements({"date": "2026-06-15"}, [])
    assert resp.runners == []
    assert resp.date == "2026-06-15"
