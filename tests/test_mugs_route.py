"""Tests for the Mugs (Tab 1) builder — reuse-first against /api/curated +
RA Crawler + scraped /best-of-day summaries."""
from nm_v1.services.mugs_today import build_today


def _curated(*picks, field="best_of_day"):
    return {
        "date": "2026-06-15",
        field: list(picks),
    }


def _pick(track="Randwick", race_number=6, tab_number=4, horse="Brutalina",
          tab_price=4.50, ai_price=3.4, clone_price=3.8, bod_source="primary"):
    return {
        "track": track, "race_number": race_number, "tab_number": tab_number,
        "horse": horse, "tab_price": tab_price,
        "ai_price": ai_price, "clone_price": clone_price,
        "bod_source": bod_source,
    }


def _ra(track="Randwick", race_no=6, race_time="14:35"):
    return {"track": track, "race_no": race_no, "raceTime": race_time, "date": "2026-06-15"}


def _summaries(v1=None, v2=None):
    return {"v1": v1 or {}, "v2": v2 or {}}


def test_returns_two_lanes_in_order():
    resp = build_today(_curated(_pick()))
    assert [lane.key for lane in resp.lanes] == ["v1", "v2"]
    assert resp.lanes[0].name == "Best of Day"
    assert resp.lanes[1].name == "Career Class"


def test_v1_picks_under_v1_lane():
    resp = build_today(_curated(_pick(horse="V1Pick"), field="best_of_day"))
    v1 = next(l for l in resp.lanes if l.key == "v1")
    v2 = next(l for l in resp.lanes if l.key == "v2")
    assert len(v1.picks) == 1
    assert v1.picks[0].horse == "V1Pick"
    assert v2.picks == []


def test_v2_picks_under_v2_lane():
    payload = {"date": "2026-06-15", "best_of_day_v2_career": [_pick(horse="V2Pick")]}
    resp = build_today(payload)
    v1 = next(l for l in resp.lanes if l.key == "v1")
    v2 = next(l for l in resp.lanes if l.key == "v2")
    assert v1.picks == []
    assert len(v2.picks) == 1
    assert v2.picks[0].horse == "V2Pick"


def test_pick_model_price_averages_ai_and_clone():
    resp = build_today(_curated(_pick(ai_price=4.0, clone_price=6.0)))
    assert resp.lanes[0].picks[0].model_price == 5.0


def test_pick_market_price_from_tab_price():
    resp = build_today(_curated(_pick(tab_price=4.5)))
    assert resp.lanes[0].picks[0].market_price == 4.5


def test_role_falls_back_to_primary_when_unknown():
    resp = build_today(_curated(_pick(bod_source="weird")))
    assert resp.lanes[0].picks[0].role == "primary"


def test_fallback_role_preserved():
    resp = build_today(_curated(_pick(bod_source="fallback")))
    assert resp.lanes[0].picks[0].role == "fallback"


def test_pick_no_crown_field_anywhere():
    """Crown language is purged from the response surface."""
    resp = build_today(_curated(_pick()))
    dumped = resp.lanes[0].picks[0].model_dump()
    assert "is_crown" not in dumped
    assert "crown" not in str(dumped).lower()


def test_race_time_joined_through_ra_crawler():
    resp = build_today(_curated(_pick()), [_ra()])
    assert resp.lanes[0].picks[0].race_time == "14:35"


def test_summary_attached_to_lanes():
    summaries = _summaries(
        v1={"picks": 37, "settled": 33, "wins": 15, "strike_pct": 45.5, "roi_pct": -6.5},
        v2={"picks": 12, "settled": 8, "wins": 6, "strike_pct": 75.0, "roi_pct": 50.6},
    )
    resp = build_today(_curated(_pick()), bod_summaries=summaries, days=30)
    v1 = next(l for l in resp.lanes if l.key == "v1")
    v2 = next(l for l in resp.lanes if l.key == "v2")
    assert v1.summary.strike_pct == 45.5
    assert v1.summary.roi_pct == -6.5
    assert v1.summary.days == 30
    assert v2.summary.strike_pct == 75.0
    assert v2.summary.roi_pct == 50.6


def test_summary_zeroes_when_scrape_fails():
    """No scrape data → lane summary is zero/None rather than 500ing."""
    resp = build_today(_curated(_pick()), bod_summaries={})
    v1 = next(l for l in resp.lanes if l.key == "v1")
    assert v1.summary.picks == 0
    assert v1.summary.roi_pct is None
    assert v1.picks  # still has today's picks


def test_empty_curated_payload_returns_empty_lanes():
    resp = build_today({"date": "2026-06-15"})
    assert resp.date == "2026-06-15"
    assert all(lane.picks == [] for lane in resp.lanes)
