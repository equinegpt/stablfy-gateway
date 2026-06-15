"""Ask tab — Gemini tool declarations + executor.

Each tool maps onto a service we already expose. The executor caches today's
/picks payload so multiple mug/race/field tool calls in one conversation only
fetch it once. PF and racing-db tools fetch on demand.
"""
from __future__ import annotations

from typing import Any

from nm_v1.clients.punting_form import fetch_ireel, fetch_speedmap
from nm_v1.clients.racing_db import get_horse_record, search_horses
from nm_v1.clients.stablfy_social import fetch_picks
from nm_v1.services.horse import build_deep_dive, pick_best_match
from nm_v1.services.mugs import build_response
from nm_v1.services.races import build_race_detail, build_races_index
from nm_v1.services.sectionals import build_sectionals
from nm_v1.services.speedmap import build_speedmap
from nm_v1.services.voices import parse_race_id

SYSTEM_PROMPT = """You are the assistant inside NO MUGS PUNTING, an Australian horse-racing app.

Use the tools to answer questions about today's racing: Mugs, races, fields, speed maps, sectionals and individual horses. A "Mug" is a runner where multiple independent AI models agree on it — a Full Mug = all our models agree, Half Mug = most, Splash = a couple. Lean on the tools rather than guessing; if a tool returns no data, say so plainly.

Rules you must follow:
- Refer to the prediction models collectively as "our models", or by the names "Gemini" and "Clone" only. NEVER name any other internal model or rating system.
- NEVER mention bookmakers or bookmaker tips (Sportsbet, Ladbrokes, Betfair, TAB) — talk only about our models and Punting Form data.
- Keep answers concise and punter-friendly. This is for entertainment only — never promise winners or give guarantees.
- race_id format is "<meetingId>-R<raceNumber>", e.g. "239793-R1". Use list_races or get_today_mugs to discover valid race_ids before calling race-specific tools.
"""

TOOL_DECLARATIONS: list[dict] = [
    {
        "name": "get_today_mugs",
        "description": "Today's Mugs — runners where multiple AI models agree. Returns full/half/splash mugs with meeting, race, horse, tab number and prices.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "list_races",
        "description": "List today's meetings and their races, with runner counts, mug counts and each race's top mug level.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_race_field",
        "description": "Full field for one race: every runner with mug status, model/market prices and career form. Needs a race_id.",
        "parameters": {
            "type": "object",
            "properties": {"race_id": {"type": "string", "description": "e.g. '239793-R1'"}},
            "required": ["race_id"],
        },
    },
    {
        "name": "get_speedmap",
        "description": "Speed map for a race: each runner's predicted settle band (leaders / on pace / midfield / back).",
        "parameters": {
            "type": "object",
            "properties": {"race_id": {"type": "string"}},
            "required": ["race_id"],
        },
    },
    {
        "name": "get_sectionals",
        "description": "Each runner's last-600m sectional from their most recent start, with track/distance/condition context.",
        "parameters": {
            "type": "object",
            "properties": {"race_id": {"type": "string"}},
            "required": ["race_id"],
        },
    },
    {
        "name": "get_horse",
        "description": "Deep-dive on a horse by name: breeding, trainer, career record and recent starts.",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
]

MUGS_IN_TOOL_RESULT = 20


class AskContext:
    """Per-request cache so repeated mug/race/field tools share one picks fetch."""

    def __init__(self) -> None:
        self._picks: dict | None = None

    async def picks(self) -> dict:
        if self._picks is None:
            self._picks = await fetch_picks(None)
        return self._picks


async def execute_tool(name: str, args: dict[str, Any], ctx: AskContext) -> dict:
    if name == "get_today_mugs":
        resp = build_response(await ctx.picks())
        data = resp.model_dump()
        data["mugs"] = data["mugs"][:MUGS_IN_TOOL_RESULT]
        return data

    if name == "list_races":
        return build_races_index(await ctx.picks()).model_dump()

    if name == "get_race_field":
        detail = build_race_detail(await ctx.picks(), args.get("race_id", ""))
        return detail.model_dump() if detail else {"error": "race not found"}

    if name == "get_speedmap":
        parsed = parse_race_id(args.get("race_id", ""))
        if parsed is None:
            return {"error": "race_id has no PF meeting id"}
        smap = build_speedmap(await fetch_speedmap(*parsed), args["race_id"])
        return smap.model_dump() if smap else {"error": "no speed map"}

    if name == "get_sectionals":
        parsed = parse_race_id(args.get("race_id", ""))
        if parsed is None:
            return {"error": "race_id has no PF meeting id"}
        sect = build_sectionals(await fetch_ireel(*parsed), args["race_id"])
        return sect.model_dump() if sect else {"error": "no sectionals"}

    if name == "get_horse":
        horse_name = args.get("name", "")
        candidates = await search_horses(horse_name)
        match = pick_best_match(horse_name, candidates)
        if match is None or not match.get("horse_code"):
            return {"error": "horse not found"}
        deep_dive = build_deep_dive(await get_horse_record(str(match["horse_code"])))
        return deep_dive.model_dump() if deep_dive else {"error": "no record"}

    return {"error": f"unknown tool {name}"}
