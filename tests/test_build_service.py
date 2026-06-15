"""Tests for the Build (Stable Brain) response normalisation."""
from nm_v1.services.build import normalize_build_result


def test_normalize_structured_with_roi():
    result = {
        "answer": "14 closers at Caulfield matched.",
        "mode": "structured",
        "n": 14,
        "runners": [{"x": 1}],
        "roi": {
            "n_settled": 12, "n_unsettled": 2, "wins": 5, "places": 8,
            "strike_pct": 41.7, "place_pct": 66.7, "roi_pct": 18.4,
            "avg_winning_sp": 4.2, "confidence": "moderate",
            # extra fields the upstream includes that we ignore:
            "total_stake": 120.0, "pnl": 22.1, "stake_per_bet": 10.0,
        },
    }
    out = normalize_build_result(result)
    assert out.mode == "structured"
    assert out.n == 14
    assert out.answer.startswith("14 closers")
    assert out.roi is not None
    assert out.roi.strike_pct == 41.7
    assert out.roi.roi_pct == 18.4
    assert out.roi.confidence == "moderate"


def test_normalize_no_tool_no_roi():
    result = {"answer": "I can't answer that from the data.", "mode": "no_tool", "n": 0, "roi": None}
    out = normalize_build_result(result)
    assert out.mode == "no_tool"
    assert out.n == 0
    assert out.roi is None
    assert out.error is None


def test_normalize_error_mode():
    result = {"answer": "", "mode": "error", "n": 0, "error": "bad SQL"}
    out = normalize_build_result(result)
    assert out.mode == "error"
    assert out.error == "bad SQL"
    assert out.roi is None


def test_normalize_missing_fields_defaults():
    out = normalize_build_result({})
    assert out.answer == ""
    assert out.mode == ""
    assert out.n == 0
    assert out.roi is None
