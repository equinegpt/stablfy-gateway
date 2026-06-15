"""Unit tests for the Mug ladder service.

Runs fully offline against synthetic /picks payloads. No env vars required.
"""
from nm_v1.services.mugs import _entry_to_mug, build_response
from nm_v1.services.voices import classify


def _entry(**overrides):
    base = {
        "meeting_id": 239417,
        "track": "Randwick",
        "race_number": 6,
        "tab_number": 4,
        "horse": "Brutalina",
        "ai_price": 3.50,
        "tab_price": 4.50,
        "skynet_rank": None,
        "clone_rank": None,
        "clone_price": None,
        "pfai_rank": None,
        "pfai_price": None,
        "gemini_position": "",
    }
    base.update(overrides)
    return base


def test_classify_levels():
    assert classify(4) == "full"
    assert classify(3) == "half"
    assert classify(2) == "splash"
    assert classify(1) is None
    assert classify(0) is None


def test_entry_full_mug():
    e = _entry(skynet_rank=1, clone_rank=1, clone_price=3.80, pfai_rank=1,
              pfai_price=4.00, gemini_position="AI_BEST")
    m = _entry_to_mug(e)
    assert m is not None
    assert m.mug_level == "full"
    assert m.voices_agree == 4
    assert set(m.named_voices_agree) == {"gemini", "clone"}
    assert m.other_voices_agree == 2
    assert m.race_id == "239417-R6"
    assert m.meeting == "Randwick"
    assert m.market_price == 4.50
    assert m.model_price == round((3.50 + 3.80 + 4.00) / 3, 2)


def test_entry_half_mug_named_and_anon_mix():
    e = _entry(skynet_rank=1, clone_rank=1, pfai_rank=3, gemini_position="AI_BEST")
    m = _entry_to_mug(e)
    assert m.mug_level == "half"
    assert m.voices_agree == 3
    assert set(m.named_voices_agree) == {"gemini", "clone"}
    assert m.other_voices_agree == 1


def test_entry_splash_clone_plus_anon():
    e = _entry(skynet_rank=1, clone_rank=1, pfai_rank=3, gemini_position="DANGER")
    m = _entry_to_mug(e)
    assert m.mug_level == "splash"
    assert m.voices_agree == 2
    assert set(m.named_voices_agree) == {"clone"}
    assert m.other_voices_agree == 1


def test_entry_one_voice_not_a_mug():
    e = _entry(skynet_rank=2, clone_rank=1, pfai_rank=3, gemini_position="")
    assert _entry_to_mug(e) is None


def test_entry_zero_voices_not_a_mug():
    e = _entry(skynet_rank=4, clone_rank=2, pfai_rank=3, gemini_position="DANGER")
    assert _entry_to_mug(e) is None


def test_gemini_value_does_not_count_as_voice():
    """Only gemini_position == 'AI_BEST' counts. DANGER/VALUE are different signals."""
    for pos in ("VALUE", "DANGER", "", None):
        e = _entry(skynet_rank=2, clone_rank=2, pfai_rank=2, gemini_position=pos)
        assert _entry_to_mug(e) is None


def test_build_response_strips_bookmaker_fields():
    """SB/LB consensus_* and tier_suggestion must never appear on a Mug."""
    e = _entry(
        skynet_rank=1, clone_rank=1, pfai_rank=1, gemini_position="AI_BEST",
        consensus_agree=4,
        consensus_sources=["sportsbet", "ladbrokes"],
        consensus_weight=12,
        tier_suggestion="HARD",
        bookies_agree=2,
    )
    picks = {"date": "2026-05-15", "full_card": {"Randwick": [e]}}
    resp = build_response(picks)
    assert resp.date == "2026-05-15"
    assert len(resp.mugs) == 1
    dumped = resp.mugs[0].model_dump()
    for forbidden in ("consensus_agree", "consensus_sources", "consensus_weight",
                      "tier_suggestion", "bookies_agree"):
        assert forbidden not in dumped


def test_build_response_orders_by_promotion_composite():
    entries = [
        _entry(meeting_id=1, track="A", race_number=1, horse="Splash1",
               skynet_rank=1, clone_rank=1, pfai_rank=3, gemini_position="",
               tab_price=5.0),
        _entry(meeting_id=2, track="B", race_number=2, horse="Full1",
               skynet_rank=1, clone_rank=1, pfai_rank=1, gemini_position="AI_BEST",
               tab_price=7.0),
        _entry(meeting_id=3, track="C", race_number=3, horse="Half_long",
               skynet_rank=1, clone_rank=1, pfai_rank=3, gemini_position="AI_BEST",
               tab_price=3.0),
        _entry(meeting_id=4, track="D", race_number=4, horse="Half_short",
               skynet_rank=1, clone_rank=1, pfai_rank=3, gemini_position="AI_BEST",
               tab_price=2.5),
    ]
    picks = {"date": "2026-05-15", "full_card": {"X": entries}}
    resp = build_response(picks)
    assert [m.mug_level for m in resp.mugs] == ["full", "half", "half", "splash"]
    # Among the two halves, the shorter market price comes first.
    assert resp.mugs[1].horse_name == "Half_short"
    assert resp.mugs[2].horse_name == "Half_long"


def test_build_response_handles_empty_full_card():
    resp = build_response({"date": "2026-05-15", "full_card": {}})
    assert resp.mugs == []
    assert resp.date == "2026-05-15"


def test_build_response_handles_missing_full_card():
    resp = build_response({"date": "2026-05-15"})
    assert resp.mugs == []


def test_race_id_falls_back_to_track_slug_when_no_meeting_id():
    e = _entry(meeting_id=None, track="Eagle Farm", race_number=3,
               skynet_rank=1, clone_rank=1, pfai_rank=1, gemini_position="AI_BEST")
    m = _entry_to_mug(e)
    assert m is not None
    assert m.race_id == "eagle-farm-R3"
