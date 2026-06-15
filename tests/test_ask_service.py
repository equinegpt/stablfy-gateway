"""Tests for the Ask tool declarations + offline (picks-based) tool execution."""
from nm_v1.services.ask import TOOL_DECLARATIONS, AskContext, execute_tool


def _picks():
    return {
        "date": "2026-05-22",
        "full_card": {
            "Geelong": [
                {"meeting_id": 1, "track": "Geelong", "race_number": 1, "tab_number": 2,
                 "horse": "FullMug", "skynet_rank": 1, "clone_rank": 1, "pfai_rank": 1,
                 "gemini_position": "AI_BEST", "tab_price": 3.5, "ai_price": 3.4,
                 "clone_price": 3.6, "pfai_price": 3.5, "career_starts": 10, "career_wins": 2,
                 "forms_wins_last5": 1, "forms_places_last5": 3},
                {"meeting_id": 1, "track": "Geelong", "race_number": 1, "tab_number": 3,
                 "horse": "NoMug", "skynet_rank": 4, "clone_rank": 5, "pfai_rank": 6,
                 "gemini_position": ""},
            ],
        },
    }


def _ctx():
    ctx = AskContext()
    ctx._picks = _picks()
    return ctx


def test_tool_declarations_wellformed():
    names = {t["name"] for t in TOOL_DECLARATIONS}
    assert {"get_today_mugs", "list_races", "get_race_field",
            "get_speedmap", "get_sectionals", "get_horse"} <= names
    for t in TOOL_DECLARATIONS:
        assert t["description"]
        assert t["parameters"]["type"] == "object"


async def test_execute_get_today_mugs():
    result = await execute_tool("get_today_mugs", {}, _ctx())
    assert any(m["horse_name"] == "FullMug" for m in result["mugs"])


async def test_execute_list_races():
    result = await execute_tool("list_races", {}, _ctx())
    assert result["meetings"][0]["meeting"] == "Geelong"


async def test_execute_get_race_field():
    result = await execute_tool("get_race_field", {"race_id": "1-R1"}, _ctx())
    assert result["runner_count"] == 2
    assert result["mug_count"] == 1


async def test_execute_get_race_field_not_found():
    result = await execute_tool("get_race_field", {"race_id": "9-R9"}, _ctx())
    assert "error" in result


async def test_execute_speedmap_bad_raceid_no_network():
    # Non-numeric prefix → no PF meeting id → error returned without any PF call.
    result = await execute_tool("get_speedmap", {"race_id": "slug-R1"}, _ctx())
    assert "error" in result


async def test_execute_unknown_tool():
    result = await execute_tool("nope", {}, _ctx())
    assert "error" in result
