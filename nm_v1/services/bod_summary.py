"""Parser for the public `/best-of-day` HTML page.

Extracts the rolling summary stats (picks / settled / wins / strike / ROI / etc)
for each variant (V1 BoD live, V2 Career Class experimental). These numbers
aren't exposed as JSON anywhere else — scraping is the least-bad option until
a proper rollup endpoint lands.

Summary line format (from server.py:2563):
    "<b>37</b> picks · <b>33</b> settled · <b>15</b> wins (<b>45.5%</b>) ·
     <b>26</b> places (78.8%) · 1 no-run · avg win SP $2.06 ·
     ROI -6.5% · P&L $-43"
"""
from __future__ import annotations

import html as html_mod
import re
from typing import Any


def _strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", " ", s)


def _collapse_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _section_for(html: str, variant_id: str) -> str | None:
    """Returns the HTML block starting at the variant's <h2 id='vN'> up to
    the next h2 or </body>. None if not found."""
    pattern = (
        rf"<h2[^>]*id=['\"]{variant_id}['\"][^>]*>.*?(?=<h2|</body)"
    )
    match = re.search(pattern, html, re.S | re.I)
    return match.group(0) if match else None


def _parse_summary_text(text: str) -> dict[str, Any]:
    """Extract the metrics from the rendered summary string."""
    out: dict[str, Any] = {}

    pairs = [
        ("picks",       r"(\d+)\s+picks"),
        ("settled",     r"(\d+)\s+settled"),
        ("wins",        r"(\d+)\s+wins"),
        ("places",      r"(\d+)\s+places"),
        ("no_run",      r"(\d+)\s+no-run"),
    ]
    for key, pattern in pairs:
        m = re.search(pattern, text, re.I)
        if m:
            out[key] = int(m.group(1))

    # Strike % is in the parens right after "wins"
    m = re.search(r"wins\s*\(\s*([\d.]+)\s*%\s*\)", text, re.I)
    if m:
        out["strike_pct"] = float(m.group(1))
    # Place % in the parens after "places"
    m = re.search(r"places\s*\(\s*([\d.]+)\s*%\s*\)", text, re.I)
    if m:
        out["place_pct"] = float(m.group(1))

    m = re.search(r"avg\s+win\s+SP\s+\$([\d.]+)", text, re.I)
    if m:
        out["avg_winning_sp"] = float(m.group(1))

    m = re.search(r"ROI\s+([+-]?[\d.]+)\s*%", text, re.I)
    if m:
        out["roi_pct"] = float(m.group(1))

    m = re.search(r"P&L\s+\$([+-]?[\d.]+)", text, re.I)
    if m:
        out["profit"] = float(m.group(1))

    return out


def parse_bod_summaries(html: str) -> dict[str, dict[str, Any]]:
    """Returns `{ "v1": {...}, "v2": {...} }`. Missing variants return empty
    dicts so the caller can decide how to handle 'no data yet'."""
    decoded = html_mod.unescape(html)
    out: dict[str, dict[str, Any]] = {}

    for vid in ("v1", "v2"):
        section = _section_for(decoded, vid)
        if section is None:
            out[vid] = {}
            continue

        # Pull the first `<div class='summary'>...</div>` inside the section
        sum_match = re.search(r"<div class=['\"]summary['\"][^>]*>(.*?)</div>", section, re.S | re.I)
        if sum_match is None:
            out[vid] = {}
            continue

        raw_summary = sum_match.group(1)
        text = _collapse_ws(_strip_tags(raw_summary))
        out[vid] = _parse_summary_text(text)

    return out
