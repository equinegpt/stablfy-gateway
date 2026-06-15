"""Normalise Stable Brain's /api/ask envelope into our BuildResponse.

The upstream envelope varies by mode (structured / sql / horse_career / no_tool
/ error) but always carries `answer`, `mode`, `n`, and an optional `roi`. We
surface that lean subset; the narrative answer already summarises the matches.
"""
from __future__ import annotations

from typing import Any

from nm_v1.models import BuildResponse, BuildRoi


def normalize_build_result(result: dict[str, Any]) -> BuildResponse:
    roi_raw = result.get("roi")
    roi = BuildRoi.model_validate(roi_raw) if isinstance(roi_raw, dict) else None
    return BuildResponse(
        answer=result.get("answer") or "",
        mode=result.get("mode") or "",
        n=int(result.get("n") or 0),
        roi=roi,
        error=result.get("error"),
    )
