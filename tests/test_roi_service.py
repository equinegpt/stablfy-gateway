"""Tests for the ROI (Tab 6) builder — TRS payload → SystemsROIResponse."""
from nm_v1.services.roi import build_systems


def test_converts_fractions_to_percentages():
    payload = {
        "date_from": "2026-06-08", "date_to": "2026-06-15", "stake_per_tip": 10.0,
        "stats": [{
            "tip_type": "AI_BEST",
            "tips": 209, "wins": 52, "places": 70,
            "win_strike_rate": 0.2488,
            "place_strike_rate": 0.3349,
            "roi": 0.0310,
            "net_profit": 64.81,
        }],
    }
    resp = build_systems(payload)
    sys = resp.systems[0]
    assert sys.label == "AI Best"
    assert sys.strike_pct == 24.88
    assert sys.place_pct == 33.49
    assert sys.roi_pct == 3.10
    assert sys.profit == 64.81
    assert sys.sample == 209


def test_orders_canonically_and_drops_unknown():
    payload = {
        "stats": [
            {"tip_type": "VALUE",  "tips": 5, "win_strike_rate": 0.1, "roi": 0.01},
            {"tip_type": "AI_BEST","tips": 5, "win_strike_rate": 0.3, "roi": 0.02},
            {"tip_type": "DANGER", "tips": 5, "win_strike_rate": 0.2, "roi": 0.03},
            {"tip_type": "UNKNOWN","tips": 1, "win_strike_rate": 0.0, "roi": 0.0},
        ],
    }
    resp = build_systems(payload)
    assert [s.key for s in resp.systems] == ["ai_best", "danger", "value"]


def test_confidence_buckets():
    """anecdote <30, moderate <100, ok at 100+"""
    def _make(tips):
        return {"stats": [{"tip_type": "AI_BEST", "tips": tips, "win_strike_rate": 0.0, "roi": 0.0}]}
    assert build_systems(_make(5)).systems[0].confidence   == "anecdote"
    assert build_systems(_make(50)).systems[0].confidence  == "moderate"
    assert build_systems(_make(500)).systems[0].confidence == "ok"


def test_pending_placeholders_always_included():
    resp = build_systems({"stats": []})
    pending_keys = {p.key for p in resp.pending}
    assert pending_keys == {"mugs", "agreement", "clone_rank"}
    assert all(p.note for p in resp.pending)


def test_handles_empty_stats():
    resp = build_systems({})
    assert resp.systems == []
    assert len(resp.pending) == 3
