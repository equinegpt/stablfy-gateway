"""Unit tests for the speed map service. Offline, synthetic PF payloads."""
from nm_v1.services.speedmap import build_speedmap, settle_band


def test_settle_band_thresholds():
    assert settle_band(1, 10) == "lead"
    assert settle_band(2, 10) == "on_pace"
    assert settle_band(3, 10) == "on_pace"
    assert settle_band(4, 10) == "midfield"
    assert settle_band(6, 10) == "midfield"
    assert settle_band(7, 10) == "back"
    assert settle_band(12, 10) == "back"


def test_settle_band_unknown_sentinel():
    assert settle_band(25, 0) == "unknown"     # no speed data
    assert settle_band(None, 5) == "unknown"
    assert settle_band(1, 0) == "unknown"       # zero speed = no data
    assert settle_band(20, 5) == "unknown"      # sentinel threshold


def _payload(*items):
    return {"payLoad": [{"track": "Geelong", "raceNo": 1, "items": list(items)}]}


def _item(tab, name, speed, settle, barrier=1):
    return {"tabNo": tab, "runnerName": name, "speed": speed, "settle": settle, "barrier": barrier}


def test_build_speedmap_orders_lead_to_back():
    payload = _payload(
        _item(1, "Backmarker", 3, 8),
        _item(2, "Leader", 25, 1),
        _item(3, "Midfielder", 4, 5),
        _item(4, "Sentinel", 0, 25),
        _item(5, "OnPace", 5, 2),
    )
    smap = build_speedmap(payload, "239793-R1")
    assert smap is not None
    assert smap.meeting == "Geelong"
    assert [r.horse_name for r in smap.runners] == [
        "Leader", "OnPace", "Midfielder", "Backmarker", "Sentinel",
    ]
    assert [r.band for r in smap.runners] == [
        "lead", "on_pace", "midfield", "back", "unknown",
    ]


def test_build_speedmap_sentinel_has_null_settle():
    payload = _payload(_item(4, "Sentinel", 0, 25))
    smap = build_speedmap(payload, "239793-R1")
    runner = smap.runners[0]
    assert runner.band == "unknown"
    assert runner.settle is None


def test_build_speedmap_empty_payload():
    assert build_speedmap({"payLoad": []}, "239793-R1") is None
    assert build_speedmap({}, "239793-R1") is None
