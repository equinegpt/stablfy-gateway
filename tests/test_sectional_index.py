"""Tests for the Sectionals tab index builder."""
from nm_v1.services.sectional_index import build_sectional_meetings


def _ra(meeting_id, track, race_no, date="2026-06-15", race_time=None,
        distance=1100, description="A handicap", state="NSW"):
    return {
        "meetingId": meeting_id,
        "track": track,
        "race_no": race_no,
        "date": date,
        "state": state,
        "description": description,
        "distance_m": distance,
        "raceTime": race_time,
    }


def test_groups_by_meeting_id_sorts_alphabetically():
    races = [
        _ra(101, "Randwick", 1, race_time="12:00PM"),
        _ra(101, "Randwick", 2, race_time="12:30PM"),
        _ra(202, "Caulfield", 1, race_time="11:50AM"),
    ]
    resp = build_sectional_meetings(races, "2026-06-15")
    assert [m.track for m in resp.meetings] == ["Caulfield", "Randwick"]
    randwick = next(m for m in resp.meetings if m.track == "Randwick")
    assert [r.race_number for r in randwick.races] == [1, 2]
    assert randwick.races[0].race_id == "101-R1"


def test_drops_races_without_meeting_id():
    races = [
        _ra(None, "Country Track", 1),
        _ra(303, "Mainstream", 1),
    ]
    resp = build_sectional_meetings(races, "2026-06-15")
    assert len(resp.meetings) == 1
    assert resp.meetings[0].track == "Mainstream"


def test_filters_by_date():
    races = [
        _ra(101, "Randwick", 1, date="2026-06-15"),
        _ra(101, "Randwick", 2, date="2026-06-16"),
    ]
    resp = build_sectional_meetings(races, "2026-06-15")
    assert len(resp.meetings) == 1
    assert len(resp.meetings[0].races) == 1
    assert resp.meetings[0].races[0].race_number == 1


def test_dedupes_duplicate_race_no_and_prefers_populated_race_time():
    """RA Crawler returns duplicate (track, race_no) rows. Prefer one with a
    populated raceTime."""
    races = [
        _ra(101, "Randwick", 1, race_time=None),
        _ra(101, "Randwick", 1, race_time="12:00PM"),
        _ra(101, "Randwick", 1, race_time=None),
    ]
    resp = build_sectional_meetings(races, "2026-06-15")
    randwick = resp.meetings[0]
    assert len(randwick.races) == 1
    assert randwick.races[0].race_time == "12:00PM"


def test_empty_input():
    resp = build_sectional_meetings(None, "2026-06-15")
    assert resp.meetings == []
    assert resp.date == "2026-06-15"
