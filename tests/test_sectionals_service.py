"""Unit tests for the sectionals service. Offline, synthetic iReel payloads."""
from nm_v1.services.sectionals import build_sectionals, parse_in_run


def test_parse_in_run():
    parsed = parse_in_run("finish,3;settling_down,2;m800,2;m400,1;")
    assert parsed["finish"] == 3
    assert parsed["settling_down"] == 2
    assert parsed["m400"] == 1


def test_parse_in_run_handles_empty_and_garbage():
    assert parse_in_run(None) == {}
    assert parse_in_run("") == {}
    assert parse_in_run("garbage;finish,5;") == {"finish": 5}


def _runner(tab, name, sectional_data):
    return {"tabNumber": tab, "horseName": name, "sectionalData": sectional_data}


def _section(date, last600, finish, track="Ballarat", distance=1000, cond="Soft",
             last200=None, last600_class=None):
    return {
        "meetingDate": date,
        "track": {"name": track, "distance": distance, "trackCondition": cond},
        "jockey": {"inRun": f"finish,{finish};settling_down,2;m800,2;m400,1;"},
        "last600Time": last600,
        "last200Time": last200,
        "last600Class": last600_class,
    }


def _payload(*runners):
    return {"payLoad": {"number": 1, "meeting": {"track": {"name": "Geelong"}},
                        "runners": list(runners)}}


def test_build_sectionals_uses_most_recent_run():
    payload = _payload(
        _runner(3, "Immortal Triumph", [
            _section("2026-04-01", 35.50, 5),
            _section("2026-05-10", 34.68, 3),  # most recent
        ]),
    )
    sect = build_sectionals(payload, "239793-R1")
    assert sect is not None
    assert sect.meeting == "Geelong"
    assert sect.race_number == 1
    r = sect.runners[0]
    assert r.last_600m == 34.68
    assert r.finish_position == 3
    assert r.last_run_date == "2026-05-10"
    assert r.last_run_track == "Ballarat"
    assert r.last_run_distance == 1000


def test_build_sectionals_runner_without_data():
    payload = _payload(_runner(1, "FirstStarter", []))
    sect = build_sectionals(payload, "239793-R1")
    r = sect.runners[0]
    assert r.last_600m is None
    assert r.finish_position is None
    assert r.last_run_track is None


def test_build_sectionals_sorts_by_tab():
    payload = _payload(
        _runner(5, "E", [_section("2026-05-10", 34.0, 1)]),
        _runner(2, "B", [_section("2026-05-10", 35.0, 2)]),
        _runner(9, "I", []),
    )
    sect = build_sectionals(payload, "239793-R1")
    assert [r.tab_number for r in sect.runners] == [2, 5, 9]


def test_build_sectionals_empty():
    assert build_sectionals({"payLoad": {"runners": []}}, "239793-R1") is None
    assert build_sectionals({}, "239793-R1") is None


def test_runs_populated_newest_first():
    payload = _payload(_runner(3, "H", [
        _section("2026-04-01", 35.0, 5, last200=11.5, last600_class=2.0),
        _section("2026-05-10", 34.0, 3, last200=11.0, last600_class=-1.0),
        _section("2026-03-15", 36.0, 8, last200=12.0, last600_class=3.0),
    ]))
    r = build_sectionals(payload, "239793-R1").runners[0]
    assert [run.date for run in r.runs] == [
        "2026-05-10", "2026-04-01", "2026-03-15",
    ]
    assert r.runs[0].last_600m == 34.0
    assert r.runs[0].last_200m == 11.0
    assert r.runs[0].last_600_class == -1.0


def test_averages_skip_sentinel_values():
    """PF returns -999 / 999 as 'no data' sentinels — must not poison averages."""
    payload = _payload(_runner(3, "H", [
        _section("2026-05-10", 34.0, 1, last200=11.0, last600_class=-1.0),
        _section("2026-04-01", 999.99, 1, last200=999.99, last600_class=999.0),
        _section("2026-03-15", 36.0, 1, last200=12.0, last600_class=1.0),
    ]))
    r = build_sectionals(payload, "239793-R1").runners[0]
    assert r.avg_last_600m == 35.0           # (34 + 36) / 2
    assert r.avg_last_200m == 11.5           # (11 + 12) / 2
    assert r.avg_last_600_class == 0.0       # (-1 + 1) / 2


def test_averages_none_when_no_valid_data():
    payload = _payload(_runner(3, "H", []))
    r = build_sectionals(payload, "239793-R1").runners[0]
    assert r.avg_last_600m is None
    assert r.runs == []


def test_race_level_fields_surfaced():
    payload = {"payLoad": {
        "number": 5, "name": "Stayers Cup", "raceClass": "Group 1",
        "trackCondition": "Heavy 8", "distance": 2400,
        "meeting": {"track": {"name": "Flemington"}},
        "runners": [_runner(1, "H", [_section("2026-05-10", 34.0, 1)])],
    }}
    sect = build_sectionals(payload, "239793-R5")
    assert sect.meeting == "Flemington"
    assert sect.race_class == "Group 1"
    assert sect.track_condition == "Heavy 8"
    assert sect.distance == 2400
    assert sect.race_name == "Stayers Cup"
