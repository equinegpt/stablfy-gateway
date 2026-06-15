"""Canonical track-name matching for joining across upstream feeds.

Lifted from /Users/andrewholmes/web-crawl-db-api/api/backfill_meeting_ids.py
(canonical_track_name) — keeps RA Crawler and PF / stablfy-social track names
aligned so we can join picks ↔ race times without misses.

Refresh this map when new mismatches surface (a few times a year typically).
"""
from __future__ import annotations

import re


def _normalise(raw: str) -> str:
    s = (raw or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    starts = [
        ("mt ", "mount "), ("mt. ", "mount "),
        ("st ", "saint "), ("st. ", "saint "),
    ]
    for short, full in starts:
        if s.startswith(short):
            return full + s[len(short):]
    return s


_SPONSORS = [
    "sportsbet", "ladbrokes", "bet365", "picklebet",
    "thomas farms", "aquis park", "aquis", "tabtouch", "tab ",
    "southside",
]

_JUNK_WORDS = [
    "rc", "racecourse", "raceway", "race club inc", "race club incorporated",
    "race club", "park", "gh", "gardens",
]

_ALIASES = {
    "southside cranbourne": "cranbourne",
    "southside pakenham":   "pakenham",
    "fannie bay":           "darwin",
    "darwin":               "darwin",
    "rosehill gardens":     "rosehill",
    "rosehill":             "rosehill",
    "yarra glen":           "yarra valley",
    "yarra valley":         "yarra valley",
    "royal randwick":       "randwick",
    "randwick":             "randwick",
    "beaumont newcastle":   "newcastle",
    "beaumont":             "newcastle",
    "newcastle":            "newcastle",
    "devonport tapeta synthetic": "devonport synthetic",
    "devonport synthetic":  "devonport synthetic",
    "kensington":           "randwick kensington",
    "randwick kensington":  "randwick kensington",
    "cannon":               "cairns",
    "cannon park":          "cairns",
    "cairns":               "cairns",
}


def canonical_track_name(raw: str | None) -> str:
    if not raw:
        return ""
    s = _normalise(raw)
    if not s:
        return ""

    s = re.sub(r"[-,/]", " ", s)
    for sp in _SPONSORS:
        s = s.replace(sp, "")
    for jw in _JUNK_WORDS:
        s = s.replace(f" {jw} ", " ")
        if s.endswith(f" {jw}"):
            s = s[: -len(f" {jw}")]
        if s.startswith(f"{jw} "):
            s = s[len(f"{jw} "):]
    s = " ".join(s.split())
    return _ALIASES.get(s, s)
