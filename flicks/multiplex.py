"""Cinemark now-playing + coming-soon titles -> a wide-release denylist.

Subtracts current and announced wide releases the indie-set heuristics can't
see — films that play only the big chains we don't otherwise track, so they
show up at just one of our theaters with no cross-theater signal. Coming-soon
is included so advance/preview screenings of not-yet-released films are caught.

Titles come from embedded JSON-LD (no auth, no browser impersonation needed).
"""

from __future__ import annotations

import json
import re

import requests

from .filter import key

URLS = (
    "https://www.cinemark.com/movies/now-playing",
    "https://www.cinemark.com/movies/coming-soon",
)
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)

_LDJSON = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
_FORMAT = re.compile(
    r"\b(xd|imax|3d|2d|70mm|35mm|smc|d-?box|dolby(\s+cinema)?|reald|"
    r"super\s+ticket|the\s+imax\s+experience)\b",
    re.I,
)
# Anniversary/re-release events are revivals, not wide releases — don't exclude them.
_EVENT_MARKERS = ("anniversary", "re-release", "rerelease")


def wide_release_keys() -> set[str]:
    keys: set[str] = set()
    for url in URLS:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
        resp.raise_for_status()
        for name in _titles(resp.text):
            if any(marker in name.lower() for marker in _EVENT_MARKERS):
                continue
            keys.add(key(_FORMAT.sub(" ", name)))
    keys.discard("")
    return keys


def _titles(html: str) -> list[str]:
    out: list[str] = []
    for blob in _LDJSON.findall(html):
        try:
            data = json.loads(blob.strip().rstrip(";"))
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict) and item.get("@type") == "Movie" and item.get("name"):
                out.append(item["name"])
    return out
