"""Tests for the BoD HTML summary parser."""
from nm_v1.services.bod_summary import parse_bod_summaries


FIXTURE_HTML = """
<!DOCTYPE html><html><body>

<h2 id='v1' style='font-size:22px;color:#ffd700;margin-top:32px'>V1 · Live</h2>
<div class='meta' style='margin-bottom:8px'>Primary D fav + A fav fallback</div>
<div class='summary'>
  <b>37</b> picks · <b>33</b> settled · <b>15</b> wins (<b>45.5%</b>) ·
  <b>26</b> places (78.8%) · 1 no-run · avg win SP $2.06 ·
  ROI <span class='neg'>-6.5%</span> · P&amp;L $-43
</div>

<h2 id='v2'>V2 · Career Class</h2>
<div class='meta'>Primary E Career + A fallback</div>
<div class='summary'>
  <b>12</b> picks · <b>8</b> settled · <b>6</b> wins (<b>75.0%</b>) ·
  <b>7</b> places (87.5%) · 1 no-run · avg win SP $2.01 ·
  ROI <span class='pos'>+50.6%</span> · P&amp;L $+81
</div>

</body></html>
"""


def test_parses_both_variants():
    out = parse_bod_summaries(FIXTURE_HTML)
    assert "v1" in out and "v2" in out


def test_v1_metrics_match_fixture():
    v1 = parse_bod_summaries(FIXTURE_HTML)["v1"]
    assert v1["picks"] == 37
    assert v1["settled"] == 33
    assert v1["wins"] == 15
    assert v1["strike_pct"] == 45.5
    assert v1["places"] == 26
    assert v1["place_pct"] == 78.8
    assert v1["no_run"] == 1
    assert v1["avg_winning_sp"] == 2.06
    assert v1["roi_pct"] == -6.5
    assert v1["profit"] == -43.0


def test_v2_metrics_positive_signs():
    v2 = parse_bod_summaries(FIXTURE_HTML)["v2"]
    assert v2["wins"] == 6
    assert v2["strike_pct"] == 75.0
    assert v2["roi_pct"] == 50.6
    assert v2["profit"] == 81.0


def test_missing_variant_returns_empty_dict():
    html = "<html><body><h2 id='v1'>only v1</h2><div class='summary'><b>5</b> picks</div></body></html>"
    out = parse_bod_summaries(html)
    assert "v1" in out
    assert out["v2"] == {}


def test_garbage_html_returns_empty():
    out = parse_bod_summaries("<html><body>nothing here</body></html>")
    assert out == {"v1": {}, "v2": {}}
