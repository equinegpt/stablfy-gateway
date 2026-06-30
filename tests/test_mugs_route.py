"""Tests for the Mugs (Tab 1) builder.

Shape was restructured 2026-06-30 to match the upstream stablfy-social
lane system (L1/L2/L3/L4, +/- L4 ★ Gemini-confirmed). The old v1/v2
"Best of Day" + scraped /best-of-day rolling SR/ROI is gone; per-lane
audit stats are now hard-coded in mugs_today.py and refreshed when the
9-week audit re-runs upstream.
"""
from nm_v1.services.mugs_today import build_today


def _play(
    track="Randwick", race_number=6, tab_number=4, horse="Brutalina",
    tab_price=4.50, clone_price=3.8, ai_price=3.4,
    bod_source="primary", lane="L4_class",
    gemini_position=None, win_pct=33.3, career_starts=4,
):
    return {
        "track": track, "race_number": race_number, "tab_number": tab_number,
        "horse": horse, "tab_price": tab_price,
        "clone_price": clone_price, "ai_price": ai_price,
        "bod_source": bod_source, "lane": lane, "bod_source_lane": lane,
        "gemini_position": gemini_position,
        "win_pct": win_pct, "career_starts": career_starts,
    }


def _curated(best_of_day=None, lanes=None, **extra):
    return {
        "date": "2026-06-30",
        "best_of_day": list(best_of_day or []),
        "lanes": lanes or {},
        **extra,
    }


def _ra(track="Randwick", race_no=6, race_time="14:35"):
    return {"track": track, "race_no": race_no, "raceTime": race_time, "date": "2026-06-30"}


# ---------------------------------------------------------------- BoD


def test_best_of_day_picks_pass_through():
    resp = build_today(_curated(best_of_day=[_play()]))
    assert resp.date == "2026-06-30"
    assert len(resp.best_of_day) == 1
    assert resp.best_of_day[0].horse == "Brutalina"


def test_best_of_day_model_price_prefers_clone_price():
    resp = build_today(_curated(best_of_day=[_play(clone_price=3.8, ai_price=4.4)]))
    assert resp.best_of_day[0].model_price == 3.8


def test_best_of_day_model_price_falls_back_to_ai_price():
    play = _play(clone_price=None, ai_price=4.2)
    resp = build_today(_curated(best_of_day=[play]))
    assert resp.best_of_day[0].model_price == 4.2


def test_best_of_day_role_passes_through():
    resp = build_today(_curated(best_of_day=[_play(bod_source="fallback")]))
    assert resp.best_of_day[0].role == "fallback"


def test_best_of_day_unknown_role_falls_back_to_primary():
    resp = build_today(_curated(best_of_day=[_play(bod_source="weird")]))
    assert resp.best_of_day[0].role == "primary"


def test_best_of_day_source_lane_passes_through():
    resp = build_today(_curated(best_of_day=[_play(lane="L2_mid_favs")]))
    assert resp.best_of_day[0].source_lane == "L2_mid_favs"


def test_race_time_joined_through_ra_crawler():
    resp = build_today(_curated(best_of_day=[_play()]), [_ra()])
    assert resp.best_of_day[0].race_time == "14:35"


# ---------------------------------------------------------------- ★ tier


def test_star_tier_set_when_l4_and_gemini_ai_best():
    play = _play(lane="L4_class", gemini_position="AI_BEST")
    resp = build_today(_curated(best_of_day=[play]))
    assert resp.best_of_day[0].is_star_tier is True


def test_star_tier_off_for_l4_without_gemini_ai_best():
    play = _play(lane="L4_class", gemini_position=None)
    resp = build_today(_curated(best_of_day=[play]))
    assert resp.best_of_day[0].is_star_tier is False


def test_star_tier_off_for_non_l4_lane_even_with_gemini():
    play = _play(lane="L2_mid_favs", gemini_position="AI_BEST")
    resp = build_today(_curated(best_of_day=[play]))
    assert resp.best_of_day[0].is_star_tier is False


# ---------------------------------------------------------------- Lanes


def test_lanes_emitted_in_l4_l2_l1_l3_order_even_when_empty():
    resp = build_today(_curated())
    assert [lane.key for lane in resp.lanes] == [
        "L4_class", "L2_mid_favs", "L1_short_favs", "L3_maiden",
    ]


def test_lane_picks_pass_through():
    lanes = {
        "L4_class": {"name": "L4 · Class", "plays": [_play(horse="A"), _play(horse="B")]},
        "L2_mid_favs": {"name": "L2 · Mid Favs", "plays": []},
        "L1_short_favs": {"name": "L1 · Short Favs", "plays": [_play(horse="C")]},
        "L3_maiden": {"name": "L3 · Maiden", "plays": []},
    }
    resp = build_today(_curated(lanes=lanes))
    l4 = next(l for l in resp.lanes if l.key == "L4_class")
    l1 = next(l for l in resp.lanes if l.key == "L1_short_favs")
    assert [p.horse for p in l4.picks] == ["A", "B"]
    assert [p.horse for p in l1.picks] == ["C"]


def test_l4_marked_as_primary():
    resp = build_today(_curated())
    l4 = next(l for l in resp.lanes if l.key == "L4_class")
    assert l4.is_primary is True
    for other_key in ("L2_mid_favs", "L1_short_favs", "L3_maiden"):
        other = next(l for l in resp.lanes if l.key == other_key)
        assert other.is_primary is False


def test_lane_audit_stats_are_hard_coded():
    resp = build_today(_curated())
    l4 = next(l for l in resp.lanes if l.key == "L4_class")
    assert l4.audit.strike_pct == 39.1
    assert l4.audit.roi_pct == 30.5
    assert l4.audit.n == 345

    l1 = next(l for l in resp.lanes if l.key == "L1_short_favs")
    # L1 highest strike rate (short favs) but -ROI.
    assert l1.audit.strike_pct == 56.6
    assert l1.audit.roi_pct == -7.3


def test_research_lanes_dropped():
    """V/P/S lanes from upstream are deliberately not surfaced — they
    don't validate on the executable feed."""
    lanes = {
        "L4_class": {"name": "L4 · Class", "plays": []},
        "V_value": {"name": "V. Value", "plays": [_play(horse="Vstuff")]},
        "P_divergence": {"name": "P. Divergence", "plays": [_play(horse="Pstuff")]},
        "S_steam": {"name": "S. Steam", "plays": []},
    }
    resp = build_today(_curated(lanes=lanes))
    keys = [lane.key for lane in resp.lanes]
    assert "V_value" not in keys
    assert "P_divergence" not in keys
    assert "S_steam" not in keys


# ---------------------------------------------------------------- Hygiene


def test_no_crown_field_on_picks():
    """Crown belongs to a different surface (AI Agreement tab). Mugs
    must not carry the upstream is_crown/crown field on its picks."""
    resp = build_today(_curated(best_of_day=[_play()]))
    dumped = resp.best_of_day[0].model_dump()
    assert "is_crown" not in dumped
    assert "crown" not in str(dumped).lower()


def test_stakes_day_flag_passes_through():
    resp = build_today({"date": "2026-06-30", "best_of_day": [], "lanes": {}, "is_stakes_day": True, "metro_pick_count": 12})
    assert resp.is_stakes_day is True
    assert resp.metro_pick_count == 12


def test_empty_curated_payload_returns_empty_response():
    resp = build_today({"date": "2026-06-30"})
    assert resp.date == "2026-06-30"
    assert resp.best_of_day == []
    assert all(lane.picks == [] for lane in resp.lanes)
